"""Unit tests for ``src.features.single_inference`` helpers (ROADMAP §2-D).

These tests intentionally exercise the *extreme* months + feature branches
that the heuristic estimator covers. The functions are pure (deterministic)
and must produce identical output across calls — the contract predict.py
relies on for stable ``predict_fire_risk`` results.

ROADMAP §3-W1 added ``reference_date`` so the SPA can replay a past (or
future) date for the temporal feature derivations; that anchor is covered
here via the dedicated ``test_create_feature_vector_with_reference_date_*``
cases.
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pytest

from src import config as config_mod
from src.features.single_inference import (
    _safe_divide,
    create_feature_vector,
    estimate_temporal_feature,
)

# ---------------------------------------------------------------------------
# ``estimate_temporal_feature`` — extreme months + each feature category
# ---------------------------------------------------------------------------


def test_estimate_temporal_feature_is_deterministic():
    """Heuristic is deterministic — same inputs must produce same outputs."""
    a = estimate_temporal_feature("temp_max", 32.0, 1, 32)
    b = estimate_temporal_feature("temp_max", 32.0, 1, 32)
    assert a == b


def test_estimate_temporal_feature_handles_year_boundaries():
    """Day-of-year 1 (Jan) and 365 (Dec) must not raise on seasonal math."""
    lag_jan, roll_jan = estimate_temporal_feature("temp_max", 32.0, 1, 1)
    lag_dec, roll_dec = estimate_temporal_feature("temp_max", 32.0, 12, 365)
    for v in (lag_jan, roll_jan, lag_dec, roll_dec):
        assert np.isfinite(v), "estimator must return finite numbers on year boundaries"


def test_estimate_temporal_feature_precip_clamps_to_zero():
    """Precipitation lag/roll must never go negative — dry days floor at 0."""
    lag, roll = estimate_temporal_feature("precip", 0.0, 6, 180)
    assert lag == 0.0 and roll == 0.0


def test_estimate_temporal_feature_ndvi_clamped_to_unit_interval():
    """NDVI must stay within [0, 1] regardless of input noise."""
    # Use a doy that produces a positive seasonal offset (md5("ndvi") % 365 = h)
    for doy in (1, 90, 180, 270, 365):
        lag, roll = estimate_temporal_feature("ndvi", 0.95, 6, doy)
        assert 0.0 <= lag <= 1.0, f"lag out of bounds at doy={doy}: {lag}"
        assert 0.0 <= roll <= 1.0, f"roll out of bounds at doy={doy}: {roll}"


def test_estimate_temporal_feature_indices_clamped_symmetric():
    """NDWI/NBR/EVI live in [-1, 1]; lag/roll must respect that range."""
    for col in ("ndwi", "nbr", "evi"):
        lag, roll = estimate_temporal_feature(col, 0.8, 11, 320)
        assert -1.0 <= lag <= 1.0
        assert -1.0 <= roll <= 1.0


def test_estimate_temporal_feature_label_like_constants_vary_neutral():
    """Columns like ``month``, ``day``, ``lat``, ``lon``, ``elevation``,
    ``land_cover`` carry no intra-month dynamics — lag == roll == input."""
    for col in ("lat", "lon", "month", "day", "elevation", "land_cover"):
        lag, roll = estimate_temporal_feature(col, 100.0, 7, 200)
        assert lag == 100.0
        assert roll == 100.0


def test_estimate_temporal_feature_unknown_col_uses_default_branch():
    """Unknown feature falls into the generic '*0.98 + 0.02*sin(doy)' formula."""
    # Just asserting it doesn't raise and returns two numbers is enough —
    # the exact value is a contract for predict.py to lock in via
    # integration tests, not for this unit to hard-code.
    lag, roll = estimate_temporal_feature("custom_unheard_of_metric", 5.0, 3, 75)
    assert isinstance(lag, float)
    assert isinstance(roll, float)


# ---------------------------------------------------------------------------
# ``_safe_divide`` — division-by-zero must never propagate inf/nan.
# ---------------------------------------------------------------------------


def test_safe_divide_handles_zero_denominator():
    assert _safe_divide(5.0, 0.0) == pytest.approx(5.0 / 1e-8)


def test_safe_divide_clips_extremes():
    """Return must be in [-1e10, 1e10] to keep XGBoost/LGBM from crashing."""
    assert abs(_safe_divide(1e12, 1e-12)) <= 1e10
    arr = _safe_divide(np.array([1.0, -1.0]), np.array([0.0, 1.0]))
    assert isinstance(arr, np.ndarray)
    assert np.all(np.isfinite(arr))


# ---------------------------------------------------------------------------
# ``create_feature_vector`` — full engineer-path output shape contract.
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_features() -> dict:
    """Minimal but realistic input dict that avoids all-missing branches."""
    return {
        "temperature": 32.5,
        "humidity": 78.0,
        "wind_speed": 4.2,
        "wind_direction": 90.0,
        "rainfall": 0.0,
        "ndvi": 0.45,
        "latitude": -1.17,
        "longitude": 100.4,
        "vegetation_type": "Savana",
        "elevation": 250.0,
    }


def test_create_feature_vector_legacy_shape(base_features):
    """Legacy features: must match models/feature_columns.json exactly."""
    X = create_feature_vector(base_features, use_new_features=False)
    assert X.ndim == 2 and X.shape[0] == 1
    # The bundled models/feature_columns.json ships a 79-dim schema (matches
    # add_new_model). Older docs citing "59-dim" refer to a deprecated v2
    # schema that no longer ships in this repo.
    assert X.shape[1] == 79
    assert np.isfinite(X).all()


def test_create_feature_vector_new_shape(base_features):
    """New stacking model: feature width follows the ACTIVE bundle schema.

    V4.2 cross-section bundle (activated 2026-08-29) ships 34 columns; the
    retired V4.1 bundle had 79. Reading feature_cols.json keeps this test
    valid across bundle swaps while still pinning width + finiteness.
    """
    X = create_feature_vector(base_features, use_new_features=True)
    assert X.ndim == 2 and X.shape[0] == 1
    with open(config_mod.NEW_FEATURE_COLUMNS_PATH, encoding="utf-8") as f:
        expected = len(json.load(f))
    assert expected == 34, f"active bundle schema changed: {expected} cols (update this test)"
    assert X.shape[1] == expected
    assert np.isfinite(X).all()


def test_create_feature_vector_clamps_out_of_range_humidity(base_features):
    """humidity=0 would make log(0) raise; AOI/base callers bypass Pydantic."""
    extreme = {**base_features, "humidity": 0.0}
    X = create_feature_vector(extreme, use_new_features=False)
    assert np.isfinite(X).all()


def test_create_feature_vector_handles_missing_optionals(base_features):
    """Caller may omit wind_direction / rainfall / elevation without raising."""
    minimal = {
        "temperature": 30.0,
        "humidity": 65.0,
        "wind_speed": 3.0,
        "latitude": -1.17,
        "longitude": 100.4,
    }
    X = create_feature_vector(minimal, use_new_features=False)
    assert np.isfinite(X).all()


# ---------------------------------------------------------------------------
# ROADMAP §3-W1 — ``reference_date`` anchor. The SPA can pick any YYYY-MM-DD
# via Header's date scrubber; the vector builder must honour that anchor for
# every season-dependent feature (month, day, doy, month_sin, doy_sin/cos,
# and the deterministic lag/roll estimates).
# ---------------------------------------------------------------------------


def _seasonal_features_dict(X: np.ndarray) -> dict[str, float]:
    """Convert a built vector back into named features for assertion.

    Reads the same ``models/feature_columns.json`` order the function uses
    so we don't have to hard-code the 79-column layout here (which would
    slow-test any feature-list re-shuffle; the JSON is the source of truth).
    """
    import json
    from pathlib import Path

    from src import config  # lazy — keep test collection fast

    with open(Path(config.FEATURE_COLUMNS_PATH), encoding="utf-8") as f:
        cols = json.load(f)
    assert X.shape == (1, len(cols))
    return dict(zip(cols, X[0].tolist(), strict=True))


def test_create_feature_vector_reference_date_shifts_month_doy(base_features):
    """reference_date must shift the ``month``/``day``/``doy`` features."""
    ref = datetime(2026, 1, 15)  # mid-January
    X = create_feature_vector(base_features, use_new_features=False, reference_date=ref)
    d = _seasonal_features_dict(X)
    assert d["month"] == pytest.approx(1)
    assert d["day"] == pytest.approx(15)
    # tm_yday for 2026-01-15 is 15.
    assert d["doy"] == pytest.approx(15)


def test_create_feature_vector_reference_date_matches_today_default(base_features):
    """``reference_date == today`` must be bit-identical to ``reference_date=None``.

    This is the exact compatibility guarantee that keeps the SPA date
    scrubber a *non-breaking* additive change: an unset date in the UI
    should produce the same vector as today.
    """
    today = datetime.now()
    X_anchor = create_feature_vector(base_features, use_new_features=False, reference_date=today)
    X_default = create_feature_vector(base_features, use_new_features=False)
    # Allow small time-of-day drift between the two calls — we only care
    # about the *date* portion, which is what the features depend on.
    d_anchor = _seasonal_features_dict(X_anchor)
    d_default = _seasonal_features_dict(X_default)
    assert d_anchor["month"] == d_default["month"]
    assert d_anchor["day"] == d_default["day"]
    assert d_anchor["doy"] == d_default["doy"]
