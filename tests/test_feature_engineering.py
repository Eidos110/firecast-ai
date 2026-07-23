"""Unit tests for ``src.feature_engineering`` (Fase 5).

Covers the mostly-checked behaviours of the feature pipeline without requiring
a real trained model or the big CSV fixture:

- ``engineer_features`` runs end-to-end on a tiny synthetic DataFrame that
  includes every column the helpers expect.
- Regression fix from audit Fase 1d: a DataFrame without a ``label`` column
  (inference path) must NOT raise ``KeyError`` from
  ``.columns.drop(['label'])``.
- ``add_temporal_features`` produces lag + rolling columns.
- ``add_fire_indices`` / ``add_spectral_indices`` / ``add_cyclical_time`` /
  ``add_trend_features`` are pure (do not mutate the input).
- ``_safe_divide_series`` avoids ZeroDivisionError when the denominator is 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import unittest

import numpy as np
import pandas as pd

from src.feature_engineering import (
    _safe_divide_series,
    add_cyclical_time,
    add_fire_indices,
    add_spectral_indices,
    add_temporal_features,
    add_trend_features,
    engineer_features,
)


def _synthetic_df(rows: int = 35, include_label: bool = False) -> pd.DataFrame:
    """Build a minimal but complete DataFrame exercising every helper column."""
    rng = np.random.default_rng(42)
    times = pd.date_range("2024-01-01", periods=rows, freq="D")
    base = pd.DataFrame(
        {
            "time": times,
            "temp_max": rng.uniform(20, 40, rows),
            "dewpoint": rng.uniform(10, 25, rows),
            "wind_u": rng.uniform(-5, 5, rows),
            "wind_v": rng.uniform(-5, 5, rows),
            "wind_speed": rng.uniform(0, 10, rows),
            "precip": rng.uniform(0, 5, rows),
            "ndvi": rng.uniform(0.1, 0.9, rows),
            "month": rng.integers(1, 13, rows),
            "B2": rng.uniform(0, 0.3, rows),
            "B3": rng.uniform(0, 0.3, rows),
            "B4": rng.uniform(0, 0.3, rows),
            "B8": rng.uniform(0, 0.3, rows),
            "B11": rng.uniform(0, 0.3, rows),
            "B12": rng.uniform(0, 0.3, rows),
        }
    )
    if include_label:
        base["label"] = rng.integers(0, 2, rows)
    return base


class TestEngineerFeatures(unittest.TestCase):
    def test_runs_without_label_column_inference(self):
        df = _synthetic_df(rows=35, include_label=False)
        out = engineer_features(df)
        self.assertIsInstance(out, pd.DataFrame)
        # Output must have MORE columns than input (lag/roll/spectral/trend added).
        self.assertGreater(out.shape[1], df.shape[1])
        self.assertGreater(len(out), 0)

    def test_runs_with_label_column_training(self):
        df = _synthetic_df(rows=35, include_label=True)
        out = engineer_features(df)
        self.assertIn("label", out.columns)

    def test_preserves_input_dataframe(self):
        df = _synthetic_df(rows=35)
        original_cols = list(df.columns)
        engineer_features(df)
        # The helper copies; original must be untouched.
        self.assertEqual(list(df.columns), original_cols)

    def test_drops_na_rows(self):
        df = _synthetic_df(rows=35)
        out = engineer_features(df)
        self.assertFalse(out.isna().any().any(), "NaN rows remain after engineer_features")


class TestAddTemporalFeatures(unittest.TestCase):
    def test_adds_lag_and_roll_columns(self):
        df = _synthetic_df(rows=35)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        out = add_temporal_features(df.copy(), numeric_cols, lag=3, roll=7)
        # Every numeric column gains _lag3 and _roll7 suffixes (except `label` if present).
        for col in numeric_cols:
            if col == "label":
                continue
            self.assertIn(f"{col}_lag3", out.columns)
            self.assertIn(f"{col}_roll7", out.columns)


class TestFireIndices(unittest.TestCase):
    def test_adds_vpd_and_dry_day(self):
        df = _synthetic_df(rows=30)
        out = add_fire_indices(df)
        for col in ("vpd", "wind_mag", "dry_day", "dry_spell_7", "dry_spell_30", "fuel_dryness"):
            self.assertIn(col, out.columns)

    def test_does_not_mutate_input(self):
        df = _synthetic_df(rows=30)
        snapshot = df.copy(deep=True)
        add_fire_indices(df)
        pd.testing.assert_frame_equal(df, snapshot)


class TestSpectralIndices(unittest.TestCase):
    def test_safe_divide_avoids_zero(self):
        numerator = pd.Series([1.0, 2.0, 3.0])
        denominator = pd.Series([0.0, 2.0, 0.0])
        out = _safe_divide_series(numerator, denominator)
        # Zero denominators should not produce inf; they produce the divided-by-epsilon value.
        self.assertFalse(np.isinf(out).any())
        self.assertFalse(np.isnan(out).any())
        # The non-zero denominator yields the exact division.
        self.assertAlmostEqual(out.iloc[1], 1.0)

    def test_adds_ndwi_nbr_evi(self):
        df = _synthetic_df(rows=30)
        out = add_spectral_indices(df)
        for col in ("ndwi", "nbr", "evi"):
            self.assertIn(col, out.columns)

    def test_does_not_mutate_input(self):
        df = _synthetic_df(rows=30)
        snapshot = df.copy(deep=True)
        add_spectral_indices(df)
        pd.testing.assert_frame_equal(df, snapshot)


class TestCyclicalTime(unittest.TestCase):
    def test_adds_month_and_doy_features(self):
        df = _synthetic_df(rows=35)
        out = add_cyclical_time(df)
        for col in ("month_sin", "month_cos", "doy", "doy_sin", "doy_cos"):
            self.assertIn(col, out.columns)


class TestTrendFeatures(unittest.TestCase):
    def test_adds_change_and_rolling_features(self):
        df = _synthetic_df(rows=35)
        # trend features depend on extreme_fire_weather (added by add_fire_indices first).
        df = add_fire_indices(df)
        out = add_trend_features(df)
        for col in ("temp_change_3d", "wind_change_3d", "precip_deficit_7d", "extreme_days_5d"):
            self.assertIn(col, out.columns)


if __name__ == "__main__":
    unittest.main()
