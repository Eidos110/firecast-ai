"""Train/serve parity guards.

Serving must feed the model the same distribution it was trained on. The two
contracts pinned here are:

1. UNIT CONTRACT (#15) — request payload is °C / mm, while the training CSV
   stores Kelvin / meters. ``create_feature_vector`` converts at assembly time.
2. TWO-LEG STACK — V4.2 combines exactly ``[p_lgbm, p_xgb]`` through the
   LogisticRegressionCV meta-learner; the retired GRU leg must not reappear.

Artifacts note: ``add_new_model/*.pkl`` are gitignored, so bundle smoke tests
skip on fresh clones / CI; the unit contract only needs tracked JSON + CSV.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src import config as config_mod
from src.features.single_inference import create_feature_vector

REPO = Path(__file__).resolve().parents[1]
NEW_MODEL_DIR = REPO / "add_new_model"

FEATURE_COLS_PATH = NEW_MODEL_DIR / "feature_cols.json"
ENGINEERED_CSV = REPO / "data" / "processed_firecast_features_v3.csv"
SCALER_ALL_PATH = NEW_MODEL_DIR / "scaler_all.pkl"

# A mid-range Indonesian afternoon: 25 °C, 70 % RH, light rain 2 mm.
SERVE_INPUT = {
    "temperature": 25.0,
    "humidity": 70.0,
    "wind_speed": 3.0,
    "wind_direction": 45.0,
    "rainfall": 2.0,  # mm
    "ndvi": 0.4,
    "vegetation_type": "Savana",
    "latitude": -2.5,
    "longitude": 112.0,
}


def _feature_vector() -> tuple[dict, list[str]]:
    fv = create_feature_vector(
        dict(SERVE_INPUT), use_new_features=True, reference_date=datetime(2025, 8, 15)
    )
    cols = json.loads(FEATURE_COLS_PATH.read_text(encoding="utf-8"))
    assert len(cols) == fv.shape[1], "feature vector width drifted from feature_cols.json"
    return dict(zip(cols, fv[0], strict=True)), cols


class TestUnitContract(unittest.TestCase):
    """Serving must emit training units: Kelvin, meters, vpd = ΔT."""

    @classmethod
    def setUpClass(cls):
        if not FEATURE_COLS_PATH.exists() or not ENGINEERED_CSV.exists():
            raise unittest.SkipTest("feature_cols.json / engineered CSV not present")
        cls.served, cls.cols = _feature_vector()

    def test_temp_max_is_kelvin(self):
        # 25 °C input → 298.15 K, not 25.
        self.assertAlmostEqual(self.served["temp_max"], 25.0 + 273.15, places=4)

    def test_precip_is_meters(self):
        # 2 mm → 0.002 m; training precip max is 0.05 m.
        self.assertAlmostEqual(self.served["precip"], 0.002, places=6)

    def test_dewpoint_is_kelvin(self):
        # Magnus dewpoint for 25 °C / 70 % RH ≈ 19.3 °C → ≈ 292.5 K.
        self.assertGreater(self.served["dewpoint"], 290.0)
        self.assertLess(self.served["dewpoint"], 295.0)

    def test_vpd_is_temperature_difference(self):
        # Training: vpd = temp_max - dewpoint (Kelvin columns). Same value as
        # the °C difference. The old Magnus es/ea hPa form gave ~1.4 (≈15x
        # smaller than the training mean of ~21).
        expected = max(0.0, 25.0 - (self.served["dewpoint"] - 273.15))
        self.assertAlmostEqual(self.served["vpd"], expected, places=4)
        self.assertGreater(self.served["vpd"], 3.0)

    def test_key_raw_columns_within_training_range(self):
        df = pd.read_csv(ENGINEERED_CSV, usecols=["temp_max", "dewpoint", "precip", "vpd", "ndvi"])
        for col in ["temp_max", "dewpoint", "precip", "vpd", "ndvi"]:
            with self.subTest(column=col):
                self.assertGreaterEqual(
                    self.served[col], df[col].min(), f"{col} below training min (unit skew?)"
                )
                self.assertLessEqual(
                    self.served[col], df[col].max(), f"{col} above training max (unit skew?)"
                )


class TestTwoLegStacking(unittest.TestCase):
    """V4.2 cross-section bundle: no GRU leg, meta-learner over [LGB, XGB]."""

    class _LgbmStub:
        def predict(self, X, **kwargs):  # noqa: N802
            return np.full(len(X), 0.3)

    class _XgbStub:
        def predict_proba(self, X):  # noqa: N802
            p = np.full(len(X), 0.35)
            return np.column_stack([1 - p, p])

    class _Meta2Leg:
        n_features_in_ = 2

        def __init__(self):
            self.seen = None

        def predict_proba(self, X):  # noqa: N802
            self.seen = np.array(X, copy=True)
            p = np.full(len(X), 0.6)
            return np.column_stack([1 - p, p])

    def test_2leg_meta_used_when_gru_disabled(self):
        from src.predict import predict_stacking

        meta = self._Meta2Leg()
        X = np.random.RandomState(0).rand(4, 10)
        # All essential legs (lgbm/xgb/meta) are provided — the internal
        # auto-load must NOT fire and replace them with disk-loaded models
        # (that bug made a 2-leg call load the 79-feature V4.1 bundle and
        # crash the stubs with a feature-width mismatch).
        out = predict_stacking(
            X,
            self._LgbmStub(),
            self._XgbStub(),
            meta,
        )
        # The 2-leg meta saw exactly [lgb_probs, xgb_probs] and its output flowed through.
        self.assertEqual(meta.seen.shape, (4, 2))
        np.testing.assert_allclose(meta.seen[:, 0], 0.3)
        np.testing.assert_allclose(meta.seen[:, 1], 0.35)
        np.testing.assert_allclose(out, np.full(4, 0.6))


class TestLgbmBoosterScale(unittest.TestCase):
    """Native ``Booster.predict`` already applies sigmoid — never squash twice.

    The active bundle stores a native Booster. Applying sigmoid to its default
    output (a probability) maps 0.93 → 0.72 and silently corrupts the stack.
    """

    def test_booster_probabilities_are_not_squashed_twice(self):
        import joblib

        from src.predict import _safe_lgbm_predict

        model_path = NEW_MODEL_DIR / "lgb_model.pkl"
        if not model_path.exists():
            raise unittest.SkipTest("lgb_model.pkl not present (gitignored artifact)")

        booster = joblib.load(model_path)
        if type(booster).__name__ != "Booster":  # bundle changed to sklearn wrapper
            raise unittest.SkipTest(f"active LGBM leg is {type(booster).__name__}, not a Booster")

        # Feed the real 34-feature width; the values only need to be plausible.
        X = np.random.RandomState(0).normal(0.0, 1.0, size=(8, booster.num_feature()))
        expected = booster.predict(X)
        got = _safe_lgbm_predict(booster, X)
        np.testing.assert_allclose(got, expected, atol=1e-7)
        # Guard against the historic double-sigmoid: the mean must not drift
        # toward 0.5 relative to the model's own probabilities.
        self.assertAlmostEqual(float(got.mean()), float(expected.mean()), places=6)


class TestStackCalibration(unittest.TestCase):
    """P3 (2026-08-29): isotonic stack calibration — loader contract + kill-switch.

    The calibrator is an OPTIONAL bundle artifact (``calibration_isotonic.pkl``):
    legacy bundles ship without it and serving must no-op, never error.
    """

    def test_absent_calibrator_is_noop(self):
        from src.predict import load_new_model_calibration

        with patch.object(
            config_mod, "NEW_CALIBRATION_PATH", str(REPO / "_no_such_dir" / "cal.pkl")
        ):
            self.assertIsNone(load_new_model_calibration())

    def test_unsupported_calibrator_type_is_noop(self):
        import joblib

        from src.predict import load_new_model_calibration

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad_cal.pkl"
            joblib.dump({"not": "a calibrator"}, bad)
            with patch.object(config_mod, "NEW_CALIBRATION_PATH", str(bad)):
                self.assertIsNone(load_new_model_calibration())

    def test_env_disable_kills_calibration(self):
        from src.predict import load_new_model_calibration

        staging_cal = REPO / "add_new_model_v42_staging" / "calibration_isotonic.pkl"
        if not staging_cal.exists():
            raise unittest.SkipTest("staging calibrator not present")
        with (
            patch.object(config_mod, "NEW_CALIBRATION_PATH", str(staging_cal)),
            patch.dict(os.environ, {"FC_DISABLE_CALIBRATION": "1"}),
        ):
            self.assertIsNone(load_new_model_calibration())

    def test_valid_calibrator_loads(self):
        from src.predict import load_new_model_calibration

        staging_cal = REPO / "add_new_model_v42_staging" / "calibration_isotonic.pkl"
        if not staging_cal.exists():
            raise unittest.SkipTest("staging calibrator not present")
        with patch.object(config_mod, "NEW_CALIBRATION_PATH", str(staging_cal)):
            cal = load_new_model_calibration()
        self.assertIsNotNone(cal)
        self.assertTrue(hasattr(cal, "predict"))

    def test_validation_status_defaults_experimental_without_manifest(self):
        from src.predict import load_new_model_validation_status

        with patch.object(
            config_mod, "NEW_MANIFEST_PATH", str(REPO / "_no_such_dir" / "VERSION.json")
        ):
            self.assertEqual(load_new_model_validation_status(), "experimental")

    def test_validation_status_read_from_manifest(self):
        from src.predict import load_new_model_validation_status

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "VERSION.json"
            manifest.write_text(
                json.dumps({"schema": "v4.2-crosssection", "validation_status": "validated"}),
                encoding="utf-8",
            )
            with patch.object(config_mod, "NEW_MANIFEST_PATH", str(manifest)):
                self.assertEqual(load_new_model_validation_status(), "validated")

    def test_validation_status_rejects_unknown_value(self):
        from src.predict import load_new_model_validation_status

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "VERSION.json"
            manifest.write_text(json.dumps({"validation_status": "trust-me-bro"}), encoding="utf-8")
            with patch.object(config_mod, "NEW_MANIFEST_PATH", str(manifest)):
                self.assertEqual(load_new_model_validation_status(), "experimental")


class TestV42StagingBundle(unittest.TestCase):
    """End-to-end serving smoke against the V4.2 staging bundle (GRU-less).

    Points every add_new_model config path at ``add_new_model_v42_staging/``
    and runs the real ``predict_fire_risk`` — proving a 2-leg bundle loads
    (GRU optional), predicts, calibrates (isotonic, P3), and carries the
    manifest's validation status. Skips when staging artifacts are absent
    (fresh clone / CI / pre-retrain).
    """

    STAGING = REPO / "add_new_model_v42_staging"
    REQUIRED = [
        "lgb_model.pkl",
        "xgb_model.pkl",
        "scaler_all.pkl",
        "stacking_weights.pkl",
        "calibration_isotonic.pkl",
        "feature_cols.json",
        "train_stats.json",
        "threshold_config.json",
        "VERSION.json",
    ]

    @classmethod
    def setUpClass(cls):
        if not all((cls.STAGING / f).exists() for f in cls.REQUIRED):
            raise unittest.SkipTest("V4.2 staging bundle not present (run notebook first)")

    def setUp(self):
        from unittest.mock import patch as mock_patch

        from src import config

        s = self.STAGING
        self._patchers = [
            mock_patch.object(config, "NEW_MODEL_DIR", str(s)),
            mock_patch.object(config, "NEW_LGBM_MODEL_PATH", str(s / "lgb_model.pkl")),
            mock_patch.object(config, "NEW_XGB_MODEL_PATH", str(s / "xgb_model.pkl")),
            mock_patch.object(config, "NEW_META_MODEL_PATH", str(s / "stacking_weights.pkl")),
            mock_patch.object(config, "NEW_SCALER_PATH", str(s / "scaler_all.pkl")),
            mock_patch.object(config, "NEW_FEATURE_COLUMNS_PATH", str(s / "feature_cols.json")),
            mock_patch.object(config, "NEW_THRESHOLD_PATH", str(s / "threshold_config.json")),
            mock_patch.object(config, "NEW_CALIBRATION_PATH", str(s / "calibration_isotonic.pkl")),
            mock_patch.object(config, "NEW_MANIFEST_PATH", str(s / "VERSION.json")),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_predict_fire_risk_on_v42_bundle(self):
        from src.predict import (
            load_new_model_calibration,
            load_new_model_validation_status,
            load_stacking_models,
            predict_fire_risk,
        )

        lgbm, xgb, meta = load_stacking_models()
        self.assertIsNotNone(lgbm)
        self.assertIsNotNone(xgb)
        self.assertEqual(getattr(meta, "n_features_in_", None), 2)
        self.assertIsNotNone(load_new_model_calibration(), "P3 calibrator must load")
        self.assertEqual(
            load_new_model_validation_status(), "validated", "manifest badge must be data-driven"
        )

        calibrator = load_new_model_calibration()
        payload = {
            "temperature": 29.0,
            "humidity": 65.0,
            "wind_speed": 4.0,
            "latitude": -2.5,
            "longitude": 112.0,
            "rainfall": 1.5,
            "ndvi": 0.35,
        }
        result = predict_fire_risk(dict(payload), model_type="new")
        self.assertEqual(result["status"], "success")
        self.assertTrue(0.0 <= result["risk_score"] <= 1.0)
        self.assertEqual(result["model_validation_status"], "validated")

        # Exact end-to-end contract: score = calibrator(raw score). Run once
        # with the calibrator disabled to capture the RAW stack probability,
        # then assert the calibrated run equals calibrator(raw) exactly.
        with patch.dict(os.environ, {"FC_DISABLE_CALIBRATION": "1"}):
            raw_result = predict_fire_risk(dict(payload), model_type="new")
        p_raw = float(raw_result["risk_score"])
        p_expected = float(np.atleast_1d(calibrator.predict(np.array([p_raw], dtype=float)))[0])
        self.assertAlmostEqual(
            result["risk_score"],
            p_expected,
            places=6,
            msg="serving must apply the isotonic calibrator to the raw stack probability",
        )


if __name__ == "__main__":
    unittest.main()
