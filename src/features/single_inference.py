"""Single-sample inference helpers (audit Fase 3a).

Contains lag/roll temporal feature estimation (used when no history is
available at inference time) and the feature-vector builder that maps raw
API inputs into the engineered feature space the production models expect.

Heavy or domain-specific code (the actual feature engineering formulas) is
still located in :mod:`src.predict`; the helpers below are stable entry
points that can be evolved independently of predict.py's structure.
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def estimate_temporal_feature(
    col_name: str, current_val: float, month: int, doy: int
) -> tuple[float, float]:
    """Estimate lag3 (3 days ago) and roll7 (7-day average) values for a
    feature given its current value. Uses deterministic heuristics derived
    from typical temporal dynamics of meteorological and spectral variables.

    This replaces the previous buggy implementation that used current values
    for both lag and roll, which caused constant predictions.
    """

    def clamp(v, vmin=None, vmax=None, rounded=False):
        if rounded:
            v = int(round(v))
        if vmin is not None:
            v = max(vmin, v)
        if vmax is not None:
            v = min(vmax, v)
        return v

    # Seasonal sine phase offset per feature (deterministic hash, NOT Python
    # random/salted hash, so the estimate reproduces across calls).
    phase = int(hashlib.md5(col_name.encode()).hexdigest(), 16) % 365
    seasonal = 0.1 * math.sin(2 * math.pi * (doy + phase) / 365)

    if col_name in ("temp_max", "dewpoint"):
        lag_val = current_val - 2.0 + 0.5 * math.sin(2 * math.pi * doy / 365) + seasonal
        roll_val = current_val - 0.8
    elif col_name == "precip":
        lag_val = max(0.0, current_val * 0.3)
        roll_val = max(0.0, current_val * 0.6)
    elif col_name in ("wind_speed", "wind_u", "wind_v"):
        lag_val = current_val * 0.95 + 0.1
        roll_val = current_val * 0.98
    elif col_name in ("B2", "B3", "B4", "B8", "B11", "B12"):
        lag_val = current_val * 0.98
        roll_val = current_val * 0.995
    elif col_name == "ndvi":
        lag_val = clamp(current_val * 0.98 + 0.02, 0.0, 1.0)
        roll_val = clamp(current_val * 0.995 + 0.005, 0.0, 1.0)
    elif col_name in ("ndwi", "nbr", "evi"):
        lag_val = clamp(current_val * 0.98, -1.0, 1.0)
        roll_val = clamp(current_val * 0.995, -1.0, 1.0)
    elif col_name == "vpd":
        lag_val = current_val + 0.2 * math.sin(2 * math.pi * doy / 365)
        roll_val = current_val
    elif col_name == "wind_mag":
        lag_val = current_val * 0.96
        roll_val = current_val * 0.99
    elif col_name in ("dry_spell_7", "dry_spell_30"):
        lag_val = max(0, int(round(current_val * 0.9)))
        roll_val = max(0, current_val * 0.95)
    elif col_name == "fuel_dryness":
        lag_val = current_val * 0.98
        roll_val = current_val * 0.99
    elif col_name == "extreme_fire_weather":
        lag_val = max(0, current_val - 0.2)
        roll_val = max(0, current_val - 0.1)
    elif col_name == "extreme_days_5d":
        lag_val = max(0, current_val - 0.1)
        roll_val = max(0, current_val - 0.05)
    elif col_name == "precip_deficit_7d":
        lag_val = current_val + 0.5
        roll_val = current_val + 0.2
    elif col_name in ("temp_change_3d", "wind_change_3d"):
        lag_val = current_val * 0.5
        roll_val = current_val * 0.7
    elif col_name in ("elevation", "land_cover", "lat", "lon", "month", "day"):
        lag_val = current_val
        roll_val = current_val
    else:
        lag_val = current_val * 0.98 + 0.02 * math.sin(doy)
        roll_val = current_val * 0.99

    return lag_val, roll_val


def create_feature_vector(features: dict[str, Any], use_new_features: bool = False) -> np.ndarray:
    """Build a (1, n_features) engineered feature vector from input dict.

    The full implementation lives in :func:`src.predict._create_feature_vector`
    — until that body is fully migrated here, this function delegates to it
    so callers importing :mod:`src.features.single_inference` get a stable
    path while predict.py's internal structural changes stay under review.
    """
    from src.predict import _create_feature_vector as _impl  # noqa: F401

    return _impl(features, use_new_features=use_new_features)
