"""Single-sample inference helpers: request features → model feature vector.

The active V4.2 bundle consumes 34 cross-section features (see
``add_new_model/feature_cols.json``). Two builders exist:

* :func:`estimate_temporal_feature` — deterministic lag3/roll7 heuristic kept
  for the legacy CNN+LGBM feature set. V4.2 does not use lag/roll columns.
* :func:`create_feature_vector` — assembles the request dictionary
  (temperature/humidity/wind/rainfall/NDVI/bands) into the ordered numeric
  vector, converting user units (°C, mm) to training units (Kelvin, meters).

``src.predict._create_feature_vector`` is a thin re-export of this module.
Optional imports stay inside functions so sandboxes without pandas/GEE can
still import the helper.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _safe_divide(
    numerator: float | np.ndarray, denominator: float | np.ndarray, epsilon: float = 1e-8
) -> float | np.ndarray:
    """Safe division to prevent division by zero and numerical overflow.

    Mirrors :func:`src.predict._safe_divide` verbatim — feature engineering
    expects the same clipping thresholds. Imported locally (instead of
    importing from predict) so this module is import-safe and self-contained.
    """
    safe_denom = denominator + epsilon
    result = numerator / safe_denom
    if isinstance(result, np.ndarray):
        return np.clip(result, -1e10, 1e10)
    return max(min(result, 1e10), -1e10)


def _load_train_stats() -> dict[str, float]:
    """Load train-only quantiles from ``add_new_model/train_stats.json``.

    These are the exact thresholds the training pipeline used for the binary
    fire-weather flags (notebook cell 2). Serving from the same file (instead
    of hardcoded °C guesses) keeps the train/serve threshold contract locked
    in one artifact. Returns ``{}`` when the file is missing (sandbox / fresh
    checkout) — callers fall back to conservative literals that match the
    training units (Kelvin / meters).
    """
    try:
        from src import config

        path = Path(config.NEW_MODEL_DIR) / "train_stats.json"
        with open(path, encoding="utf-8") as f:
            stats = json.load(f)
        if isinstance(stats, dict):
            return {k: float(v) for k, v in stats.items() if isinstance(v, (int, float))}
    except Exception:  # noqa: BLE001 — missing artifact must not break inference
        logger.warning("train_stats.json unavailable — using built-in Kelvin-unit defaults")
    return {}


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


def create_feature_vector(
    features: dict[str, Any],
    use_new_features: bool = False,
    reference_date: datetime | None = None,
) -> np.ndarray:
    """Build a ``(1, n_features)`` engineered feature vector from a request dict.

    ``src.predict`` delegates here so there is one implementation of the
    train/serve unit contract (see AGENTS.md bug #15).

    Args:
        features: Input feature dictionary. Recognised keys: ``temperature``,
            ``humidity``, ``wind_speed``, ``wind_direction``, ``rainfall``,
            ``ndvi``, ``vegetation_type``, ``latitude``, ``longitude``,
            ``elevation``, ``land_cover``, plus optional spectral bands
            ``B2, B3, B4, B8, B11, B12`` (sent by GEE).
        use_new_features: If True, order the vector by the V4.2
            ``add_new_model/feature_cols.json`` (34 features). If False, use
            the legacy CNN+LGBM ``config.FEATURE_COLUMNS_PATH``.
        reference_date: Optional anchor date for derived time features
            (``month``, ``day``, ``doy``). ROADMAP §3-W1 passes the date
            picked via the SPA Header scrubber here so engineers can replay
            "what would the risk have been on 2026-06-15?". ``None`` (the
            default) preserves the historical behaviour of anchoring to
            ``datetime.now()`` — backward compatible.

    Returns:
        2-D float numpy array of shape ``(1, len(feature_columns))``.

    Raises:
        ValueError: If the assembled vector length does not match
            ``len(feature_columns)`` — propagates; never silently returns a
            malformed vector (AGENTS.md §3 "JANGAN pernah kembalikan 0.5
            diam-diam" generalised to "JANGAN pernah kembalikan vector yang
            shape-nya salah").
    """
    # ---- extract inputs from the features dict (mirrors predict.py verbatim)
    # UNIT CONTRACT (audit 2026-08-23, bug #15): the request payload is in
    # "user" units — temperature °C, rainfall mm — but the training dataset
    # (firecast_data_readymodelling_final_V3.csv) stores temp_max/dewpoint in
    # KELVIN (mean 298.33 / 277.38) and precip in METERS (max 0.05). The
    # conversions to training units happen below, at feature-assembly time,
    # so the scalers and models receive inputs on the same scale they were
    # fitted on.
    # Defensive clamps: the HTTP layer validates /predict ranges, but AOI
    # base_features and direct library callers bypass Pydantic. A humidity of
    # 0 makes log(0) below raise and temperature near -237.7 °C divides by
    # zero in the Magnus formula; clamp to physically meaningful bounds.
    temp = float(features.get("temperature", 30))  # °C
    humidity = min(max(float(features.get("humidity", 50)), 1.0), 100.0)
    wind_speed = float(features.get("wind_speed", 5))  # m/s (same unit as training)
    wind_direction = features.get("wind_direction", 0)
    rainfall = features.get("rainfall")  # mm; Default is None (not provided)
    # Use 1.0mm for feature engineering if not provided - neutral assumption
    # (1 mm = 0.001 m ≈ training precip_mean; see base_dict assembly below)
    rainfall_numeric = 1.0 if rainfall is None else float(rainfall)
    ndvi = features.get("ndvi", 0.3)
    vegetation_type = features.get("vegetation_type", "Savana")
    lat = features.get("latitude", -2.0)
    lon = features.get("longitude", 112.0)

    # Elevation: use provided if available (from GEE), else default
    elevation = features.get("elevation", 100.0)

    # Land cover: use provided if available (from GEE Dynamic World), else map from vegetation
    if "land_cover" in features:
        land_cover = features["land_cover"]
    else:
        land_cover_map = {
            "Hutan": 10,
            "Forest": 10,
            "Hutan Tropis Lembab": 10,
            "Semak": 20,
            "Shrub": 20,
            "Semak Kering": 20,
            "Savana": 30,
            "Savanna": 30,
            "Rumput": 40,
            "Grass": 40,
            "Padang Rumput": 40,
            "Lahan Gambut": 40,
            "Lahan Pertanian": 50,
            "Agriculture": 50,
            "Lahan Terbuka": 60,
            "Open Land": 60,
            "Pemukiman": 70,
            "Settlement": 70,
        }
        land_cover = land_cover_map.get(vegetation_type, 30)

    # Convert wind direction to u/v components
    wind_rad = math.radians(wind_direction)
    wind_u = -wind_speed * math.sin(wind_rad)
    wind_v = -wind_speed * math.cos(wind_rad)

    # Get current date features. When ``reference_date`` is supplied (SPA
    # date-scrubber, ROADMAP §3-W1), derive month/day/doy from it so all
    # downstream seasonal features shift accordingly. Default: ``now()``
    # preserves the legacy behaviour exactly so callers outside the new
    # date-aware flow (e.g. tests, batch jobs) keep working unchanged.
    now = reference_date if reference_date is not None else datetime.now()
    month = now.month
    day = now.day
    doy = now.timetuple().tm_yday

    # Calculate derived meteorological features
    # Dewpoint approximation using Magnus formula (input/Output °C; converted
    # to Kelvin at feature-assembly time because training stored Kelvin).
    a = 17.271
    b = 237.7
    alpha = ((a * temp) / (b + temp)) + math.log(humidity / 100.0)
    dewpoint = (b * alpha) / (a - alpha)
    dewpoint_k = dewpoint + 273.15  # training unit
    temp_max = temp + 273.15  # training unit: temp_max is Kelvin (mean 298.33)

    # VPD — training defined this as ``temp_max - dewpoint`` (Kelvin columns,
    # notebook cell 2), i.e. a plain temperature difference. A K difference
    # equals a °C difference, so compute it in °C here; do NOT use the old
    # Magnus es/ea (hPa) variant — it produced values ~15x smaller
    # than the training distribution (mean ≈ 21).
    vpd = max(0.0, temp - dewpoint)

    # Wind magnitude
    wind_mag = math.sqrt(wind_u**2 + wind_v**2)

    # Spectral bands: use GEE-provided values if available, else synthetic
    required_bands = ["B2", "B3", "B4", "B8", "B11", "B12"]
    if all(band in features for band in required_bands):
        B2 = features.get("B2", 0.0)
        B3 = features.get("B3", 0.0)
        B4 = features.get("B4", 0.0)
        B8 = features.get("B8", 0.0)
        B11 = features.get("B11", 0.0)
        B12 = features.get("B12", 0.0)
    else:
        # Synthetic estimation based on NDVI (fallback for sandbox / no GEE)
        if ndvi > 0.6:  # Dense vegetation
            B2, B3, B4, B8, B11, B12 = 0.03, 0.05, 0.04, 0.45, 0.08, 0.05
        elif ndvi > 0.3:  # Moderate
            B2, B3, B4, B8, B11, B12 = 0.05, 0.08, 0.09, 0.30, 0.15, 0.10
        else:  # Sparse
            B2, B3, B4, B8, B11, B12 = 0.10, 0.12, 0.15, 0.12, 0.25, 0.20

    # Calculate spectral indices with safe division
    ndwi = _safe_divide(B3 - B11, B3 + B11)
    nbr = _safe_divide(B8 - B12, B8 + B12)
    evi = 2.5 * _safe_divide(B8 - B4, B8 + 6 * B4 - 7.5 * B2 + 1)

    # Fire weather indices
    # precip in training units (meters): 1 mm = 0.001 m. Training max is
    # 0.05 m, so the "< 1.0" dry-day cut (meters) is effectively always
    # true there — replicate that behaviour instead of the old mm-based
    # comparison, which produced a constant-0 feature while training was
    # constant-1 (bug #15 sub-finding).
    precip_m = rainfall_numeric / 1000.0
    dry_day = 1 if precip_m < 1.0 else 0
    dry_spell_7 = dry_day * 3  # training ramps 1..7 (rolling sum); 3 = mid-range
    dry_spell_30 = dry_day * 3  # training ramps 1..30; 3 = within range
    fuel_dryness = vpd * (1 - ndvi)

    # Threshold indicators. Training (notebook cell 2) derives every cut from
    # TRAIN-ONLY quantiles persisted in add_new_model/train_stats.json — e.g.
    # temp_max_q75 ≈ 302 K, not 32 °C. Serving must use the SAME thresholds or
    # the binary flags flip distribution (bug #15: hot_threshold was always 0
    # serving because 30 °C < 32 < 302 K compares in the wrong unit). Env
    # vars still override for experimentation.
    train_stats = _load_train_stats()
    temp_threshold = float(
        os.getenv("RISK_TEMP_THRESHOLD", str(train_stats.get("temp_max_q75", 302.4)))
    )
    vpd_threshold = float(os.getenv("RISK_VPD_THRESHOLD", str(train_stats.get("vpd_q75", 23.0))))
    wind_threshold = float(
        os.getenv("RISK_WIND_THRESHOLD", str(train_stats.get("wind_speed_q75", 4.5)))
    )

    hot_threshold = 1 if temp_max > temp_threshold else 0
    dry_threshold = 1 if vpd > vpd_threshold else 0
    windy_threshold = 1 if wind_speed > wind_threshold else 0
    extreme_fire_weather = hot_threshold + dry_threshold + windy_threshold

    # Trend features (approximated for single prediction)
    temp_change_3d = 0.0
    wind_change_3d = 0.0
    # Training: (precip.rolling(7).mean() - precip_mean).clip(lower=0) in
    # METERS — values are ~0..0.05, never the old "10 - mm*7" ≈ 3 (order of
    # magnitude out of distribution). Use the roll7 estimator in meters.
    _, precip_roll7_m = estimate_temporal_feature("precip", precip_m, month, doy)
    precip_mean = float(train_stats.get("precip_mean", 0.0016))
    precip_deficit_7d = max(0.0, precip_roll7_m - precip_mean)
    # Training: (extreme_fire_weather.rolling(5).sum() > 0).astype(int) → binary
    extreme_days_5d = 1 if extreme_fire_weather > 0 else 0

    # Cyclical time features
    month_sin = math.sin(2 * math.pi * month / 12)
    month_cos = math.cos(2 * math.pi * month / 12)
    doy_sin = math.sin(2 * math.pi * doy / 365)
    doy_cos = math.cos(2 * math.pi * doy / 365)

    # Precipitation / temp_max for downstream feature columns: both already
    # converted to training units above (precip meters, temp_max Kelvin).
    precip = precip_m

    logger.info(
        "Input features: temp=%s (C), humidity=%s, wind_speed=%s, precip=%s (m), ndvi=%s",
        temp,
        humidity,
        wind_speed,
        precip,
        ndvi,
    )

    # Build base feature dictionary
    base_dict = {
        "B11": B11,
        "B12": B12,
        "B2": B2,
        "B3": B3,
        "B4": B4,
        "B8": B8,
        "dewpoint": dewpoint_k,
        "elevation": elevation,
        "land_cover": land_cover,
        "lat": lat,
        "lon": lon,
        "ndvi": ndvi,
        "precip": precip,
        "temp_max": temp_max,
        "wind_speed": wind_speed,
        "wind_u": wind_u,
        "wind_v": wind_v,
        "month": month,
        "day": day,
    }

    # Calculate lag and rolling features using realistic estimators
    lag_features = {}
    for col, val in base_dict.items():
        lag3_val, roll7_val = estimate_temporal_feature(col, val, month, doy)
        lag_features[f"{col}_lag3"] = lag3_val
        lag_features[f"{col}_roll7"] = roll7_val

    # Combine all features
    all_features = {
        **base_dict,
        **lag_features,
        "month_sin": month_sin,
        "month_cos": month_cos,
        "doy": doy,
        "doy_sin": doy_sin,
        "doy_cos": doy_cos,
        "vpd": vpd,
        "wind_mag": wind_mag,
        "dry_day": dry_day,
        "dry_spell_7": dry_spell_7,
        "dry_spell_30": dry_spell_30,
        "fuel_dryness": fuel_dryness,
        "hot_threshold": hot_threshold,
        "dry_threshold": dry_threshold,
        "windy_threshold": windy_threshold,
        "extreme_fire_weather": extreme_fire_weather,
        "ndwi": ndwi,
        "nbr": nbr,
        "evi": evi,
        "temp_change_3d": temp_change_3d,
        "wind_change_3d": wind_change_3d,
        "precip_deficit_7d": precip_deficit_7d,
        "extreme_days_5d": extreme_days_5d,
    }

    # Load feature columns to ensure correct order
    feature_columns: list = []  # init before try to avoid UnboundLocalError in except
    try:
        # Lazy import: avoid hard dependency on src.config / src.predict at
        # import-time of this module. predict.py can still be uninitialized
        # when a test imports single_inference in isolation.
        from src import config

        if use_new_features:
            # ``load_new_feature_columns`` lives in predict.py — but to avoid
            # cyclic import (predict.py imports from this module as well) we
            # open the JSON directly here using the path attribute on config.
            feature_columns_path = config.NEW_FEATURE_COLUMNS_PATH
            with open(feature_columns_path) as f:
                feature_columns = json.load(f)
            logger.info(
                "Using new model features (%d): %s...",
                len(feature_columns),
                feature_columns[:10],
            )
        else:
            with open(config.FEATURE_COLUMNS_PATH) as f:
                feature_columns = json.load(f)
            logger.info(
                "Using legacy features (%d): %s...",
                len(feature_columns),
                feature_columns[:10],
            )

        feature_vector = []
        missing_features = []
        for col in feature_columns:
            if col in all_features:
                feature_vector.append(all_features[col])
            else:
                missing_features.append(col)
                feature_vector.append(0.0)

        if missing_features:
            logger.warning("Missing features (using 0.0): %s", missing_features)

        # CRITICAL: Feature count must match exactly
        if len(feature_vector) != len(feature_columns):
            raise ValueError(
                f"Feature count mismatch: expected {len(feature_columns)}, "
                f"got {len(feature_vector)}"
            )

        logger.debug("Feature vector shape: (%d,)", len(feature_vector))
        logger.debug("First 10 values: %s", feature_vector[:10])

        return np.array([feature_vector])
    except Exception:
        logger.error("Fatal error in create_feature_vector", exc_info=True)
        logger.error("Feature columns: %s", feature_columns)
        logger.error("Available features: %s", list(all_features.keys()))
        raise  # Propagate error — never return a malformed vector
