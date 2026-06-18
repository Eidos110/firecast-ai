"""
FireCast Prediction Engine - Frontend Integration
=================================================
Integrates with backend ML models for fire risk prediction.
"""

from __future__ import annotations

import sys
import os
import logging
import importlib.util
import traceback
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# Add parent directories to path for imports
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Demo mode flag - set to True if models can't be loaded
DEMO_MODE = False

# ---------------------------------------------------------------------------
# Module-level bootstrap diagnostics — guarantees import results appear in
# Railway runtime logs regardless of Streamlit's log-level configuration.
# MUST be before the import block so the except handler can call it.
# ---------------------------------------------------------------------------
import sys as _bs_sys

def _bs_log(msg: str) -> None:
    try:
        with open("/tmp/prediction_engine_init.log", "w", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass  # Never fail the app because of logging
    print(msg, file=_bs_sys.stderr, flush=True)


# Try to import from src using importlib
try:
    # Build a stub 'src' package with right __path__ so that any
    # submodule import (e.g. "from src.models.registry import …") can be
    # found on disk without running src/__init__.py.
    import types as _types
    src_stub = _types.ModuleType("src")
    src_stub.__path__ = [str(src_path)]
    src_stub.__package__ = "src"
    sys.modules["src"] = src_stub

    # Patch a no-op loader so that exec_module() does NOT execute the
    # real src/__init__.py (which has heavy imports).
    class _NullLoader:
        def create_module(self, spec):
            return src_stub
        def exec_module(self, mod):
            pass

    src_spec = importlib.util.spec_from_file_location(
        "src", project_root / "src" / "__init__.py",
        submodule_search_locations=[str(src_path)],
    )
    src_spec.loader = _NullLoader()
    src_mod = importlib.util.module_from_spec(src_spec)
    src_mod.__path__ = [str(src_path)]
    src_mod.__package__ = "src"
    sys.modules["src"] = src_mod

    # Import predict module
    predict_spec = importlib.util.spec_from_file_location(
        "src.predict", src_path / "predict.py"
    )
    predict_module = importlib.util.module_from_spec(predict_spec)
    sys.modules["src.predict"] = predict_module
    predict_spec.loader.exec_module(predict_module)

    predict_fire_risk = predict_module.predict_fire_risk
    PredictionError = predict_module.PredictionError
    ModelLoadError = predict_module.ModelLoadError

    # Import database module
    database_spec = importlib.util.spec_from_file_location(
        "src.database", src_path / "database.py"
    )
    database_module = importlib.util.module_from_spec(database_spec)
    sys.modules["src.database"] = database_module
    database_spec.loader.exec_module(database_module)

    log_prediction = database_module.log_prediction
    get_predictions = database_module.get_predictions
    init_db = database_module.init_db

    logger.info("✓ Models loaded successfully via importlib")

except Exception as e:
    err_msg = f"FAILED importlib attempt: {type(e).__name__}: {e}"
    logger.warning(err_msg)
    logger.warning(f"Traceback:\n{traceback.format_exc()}")
    tb = traceback.format_exc()
    import sys as _sys2
    print(f"[BOOTSTRAP] {err_msg}", file=_sys2.stderr, flush=True)
    print(f"[BOOTSTRAP] {tb}", file=_sys2.stderr, flush=True)
    _bs_log(f"[BOOTSTRAP] IMPORT FAILED: {err_msg}\n{tb}")

    try:
        # Fallback: direct import
        from src.predict import predict_fire_risk, PredictionError, ModelLoadError
        from src.database import log_prediction, get_predictions, init_db
        logger.info("✓ Models loaded via fallback import")
    except Exception as e2:
        err_msg = f"Fallback import failed: {type(e2).__name__}: {e2}"
        logger.warning(err_msg)
        logger.warning(f"Traceback: {traceback.format_exc()}")
        import sys as _sys
        print(f"[BOOTSTRAP] {err_msg}", file=_sys.stderr, flush=True)
        print(f"[BOOTSTRAP] {traceback.format_exc()}", file=_sys.stderr, flush=True)
        # Define dummy functions if src is not available
        predict_fire_risk = None
        PredictionError = Exception
        ModelLoadError = Exception
        log_prediction = None
        get_predictions = None
        init_db = lambda: None
        logger.warning("✗ DEMO MODE — models not loaded; all imports failed")
        DEMO_MODE = True  # Set demo mode flag since models unavailable

_bs_log(
    f"[BOOTSTRAP] predict_fire_risk={'OK' if predict_fire_risk else 'None'}, "
    f"DEMO_MODE={DEMO_MODE}, "
    f"Python={_bs_sys.version.split()[0]}\n"
    f"[BOOTSTRAP] path[0]={sys.path[0]!r}\n"
    f"[BOOTSTRAP] project_root={project_root!r}\n"
    f"[BOOTSTRAP] sys.modules keys: {[k for k in _bs_sys.modules if k.startswith('src')]}\n"
    f"[BOOTSTRAP] time={__import__('datetime').datetime.now().isoformat()}"
)

def _generate_demo_result(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate demo prediction result based on input parameters.
    Used when models are not available.
    """
    temp = input_data.get("temperature", 32)
    humidity = input_data.get("humidity", 45)
    wind = input_data.get("wind_speed", 5)

    # Simple risk calculation for demo
    base_risk = 0.3
    temp_factor = max(0, (temp - 30) / 20) * 0.3
    humidity_factor = max(0, (50 - humidity) / 50) * 0.25
    wind_factor = min(wind / 20, 0.2)

    risk_score = min(base_risk + temp_factor + humidity_factor + wind_factor, 0.95)

    # Determine risk level (using tolerance-adjusted thresholds)
    risk_tolerance = input_data.get("risk_tolerance", 50)
    risk_level = _get_risk_level(risk_score, risk_tolerance)

    risk_colors = {
        "Low": "#22c55e",
        "Medium": "#f59e0b",
        "High": "#f97316",
        "Extreme": "#ef4444",
    }
    risk_color = risk_colors.get(risk_level, "#f59e0b")

    # Risk factors
    risk_factors = {}
    if temp > 33:
        risk_factors["Suhu Tinggi"] = min((temp - 33) / 12 * 100, 100)
    elif temp > 28:
        risk_factors["Suhu Sedang"] = (temp - 28) / 10 * 50
    else:
        risk_factors["Suhu Normal"] = 10

    if humidity < 45:
        risk_factors["Kelembaban Rendah"] = (45 - humidity) / 45 * 100
    elif humidity < 60:
        risk_factors["Kelembaban Sedang"] = (60 - humidity) / 60 * 50
    else:
        risk_factors["Kelembaban Normal"] = 10

    if wind > 5:
        risk_factors["Angin Kuat"] = min((wind - 5) / 15 * 100, 100)
    elif wind > 2:
        risk_factors["Angin Sedang"] = (wind - 2) / 10 * 50
    else:
        risk_factors["Angin Lemah"] = 10

    # Always ensure there's at least one factor
    if not risk_factors:
        risk_factors["Cuaca Normal"] = 20

    # Generate temporal forecast
    time_steps = []
    risk_scores = []
    affected_areas = []
    current_time = datetime.now()
    for i in range(input_data.get("prediction_hours", 12)):
        # Risk varies slightly over time
        hour_risk = risk_score * (1 + 0.1 * np.sin(i / 3))
        hour_risk = max(0, min(1, hour_risk))
        time_steps.append((current_time + timedelta(hours=i)).isoformat())
        risk_scores.append(hour_risk)
        affected_areas.append(hour_risk * 100)  # Samakan dengan mode nyata

    temporal_forecast = {
        "time_steps": time_steps,
        "risk_scores": risk_scores,
        "affected_areas": affected_areas,
    }

    # Fire spread directions based on wind
    wind_dir = input_data.get("wind_direction", 0)
    spread_directions = []
    for angle_offset in [-30, 0, 30]:
        direction = (wind_dir + angle_offset) % 360
        spread_directions.append(
            {
                "direction": direction,
                "angle": direction,
                "speed_kmh": wind * 0.5,
                "probability": risk_score * (1 - abs(angle_offset) / 90),
            }
        )

    # Calculate model agreement (simulate some disagreement for demo)
    cnn_prob = risk_score + np.random.uniform(-0.05, 0.05)
    lgbm_prob = risk_score + np.random.uniform(-0.05, 0.05)
    disagreement = abs(cnn_prob - lgbm_prob)
    confidence_interval = disagreement
    model_agreement = 1 - disagreement

    return {
        "status": "demo",
        "overall_risk": risk_score,
        "risk_level": risk_level,
        "risk_color": risk_color,
        "risk_factors": risk_factors,
        "confidence": 0.75,
        "confidence_interval": float(confidence_interval),
        "model_agreement": float(model_agreement),
        "cnn_probability": float(cnn_prob),
        "lgbm_probability": float(lgbm_prob),
        "temporal_forecast": temporal_forecast,
        "spread_directions": spread_directions,
        "affected_area": risk_score * 500,  # hectares
        "max_spread_distance": risk_score * 10,  # km
        "model_type": "DEMO",
        "timestamp": datetime.now().isoformat(),
    }


def _get_risk_level(score: float, risk_tolerance: int = 50) -> str:
    """Convert score to risk level string, adjusted by risk tolerance.

    Args:
        score: Risk probability 0-1.
        risk_tolerance: 0-100 slider value. 50 = default thresholds.
            Higher tolerance = lower thresholds (more sensitive, more alerts).
            Lower tolerance = higher thresholds (less sensitive, fewer alerts).
    """
    # Shift thresholds: tolerance=100 shifts by -0.15, tolerance=0 shifts by +0.15
    offset = (50 - risk_tolerance) / 50 * 0.15
    low_thresh = 0.3 + offset
    med_thresh = 0.5 + offset
    high_thresh = 0.7 + offset

    if score < low_thresh:
        return "Low"
    elif score < med_thresh:
        return "Medium"
    elif score < high_thresh:
        return "High"
    else:
        return "Extreme"


def run_prediction(
    input_data: Dict[str, Any],
    model_version: Optional[str] = None,
    model_type: str = "new",
) -> Dict[str, Any]:
    """
    Run fire prediction with given input parameters.

    Args:
        input_data: Dictionary containing input parameters:
            - temperature: float (°C)
            - humidity: float (%)
            - wind_speed: float (m/s)
            - wind_direction: float (degrees)
            - latitude: float
            - longitude: float
            - prediction_hours: int
            - model_type: str - "legacy" or "new" (default: "new")
         model_version: Optional model version string. If None, uses active version.
         model_type: Model type - "legacy" for Model Ensemble, "new" for Model Stacking (default: "new")

    Returns:
        Dictionary with prediction results
    """
    global DEMO_MODE

    logger.info(f"Running prediction with input: {input_data}")
    logger.info(f"Using model_type: {model_type}")

    if predict_fire_risk is None:
        logger.info("Using DEMO mode (model not loaded)")
        return _generate_demo_result(input_data)

    if DEMO_MODE:
        logger.info("Running in DEMO mode")
        return _generate_demo_result(input_data)

    try:
        features = _prepare_features(input_data)

        model_type = input_data.get("model_type", model_type)

        if "active_model_type" in st.session_state:
            model_type = st.session_state["active_model_type"]

        result = predict_fire_risk(
            features, model_version=model_version, model_type=model_type
        )

        # Post-process results
        processed_result = _post_process_results(result, input_data)

        # Log prediction to database
        if log_prediction is not None:
            try:
                init_db()
                log_prediction(
                    latitude=float(input_data.get("latitude", -1.1747)),
                    longitude=float(input_data.get("longitude", 100.4012)),
                    temperature=float(input_data.get("temperature", 30)),
                    humidity=float(input_data.get("humidity", 50)),
                    wind_speed=float(input_data.get("wind_speed", 5)),
                    wind_direction=float(input_data.get("wind_direction", 0)),
                    overall_risk=processed_result.get("overall_risk", 0),
                    risk_level=processed_result.get("risk_level", "Unknown"),
                    rainfall=float(input_data.get("rainfall", 0)),
                    vegetation_type=input_data.get("vegetation_type", "Savana"),
                    confidence=processed_result.get("confidence", 0),
                    cnn_probability=processed_result.get("cnn_probability"),
                    lgbm_probability=processed_result.get("lgbm_probability"),
                    affected_area=processed_result.get("affected_area", 0),
                    max_spread_distance=processed_result.get("max_spread_distance", 0),
                    model_name=processed_result.get("model_type", "DEMO"),
                )
            except Exception as db_err:
                logger.debug(f"Prediction logging skipped: {db_err}")

        return processed_result

    except (PredictionError, ModelLoadError) as e:
        logger.error(f"Model prediction failed: {e}")
        logger.info("Falling back to DEMO mode")
        DEMO_MODE = True
        return _generate_demo_result(input_data)

    except Exception as e:
        logger.error(f"Model prediction failed: {e}")
        logger.info("Falling back to DEMO mode")
        DEMO_MODE = True
        return _generate_demo_result(input_data)


def _prepare_features(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare input data into features expected by the model.
    """
    # Base meteorological, location, and GEE-derived features
    features = {
        "temperature": float(input_data.get("temperature", 32)),
        "humidity": float(input_data.get("humidity", 45)),
        "wind_speed": float(input_data.get("wind_speed", 5)),
        "wind_direction": float(input_data.get("wind_direction", 0)),
        "rainfall": float(input_data.get("rainfall", 0)),
        "latitude": float(input_data.get("latitude", -1.1747)),
        "longitude": float(input_data.get("longitude", 100.4012)),
        "ndvi": float(input_data.get("ndvi", 0.5)),
        "vegetation_type": input_data.get("vegetation_type", "Savana"),
        "fuel_moisture": float(input_data.get("fuel_moisture", 35)),
        # GEE data (if available)
        "elevation": float(input_data.get("elevation", 100.0)),
        "B2": float(input_data.get("B2", 0.0)),
        "B3": float(input_data.get("B3", 0.0)),
        "B4": float(input_data.get("B4", 0.0)),
        "B8": float(input_data.get("B8", 0.0)),
        "B11": float(input_data.get("B11", 0.0)),
        "B12": float(input_data.get("B12", 0.0)),
    }
    # Validate coordinates
    lat = features["latitude"]
    lon = features["longitude"]
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude {lat} is out of valid range [-90, 90]")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude {lon} is out of valid range [-180, 180]")
    
    # Include land_cover only if explicitly provided (from GEE Dynamic World)
    if "land_cover" in input_data:
        features["land_cover"] = input_data["land_cover"]

    # Apply what-if overrides
    if input_data.get("is_what_if"):
        if "override_wind_speed" in input_data:
            features["wind_speed"] = float(input_data["override_wind_speed"])
        if "override_wind_direction" in input_data:
            features["wind_direction"] = float(input_data["override_wind_direction"])
        if "override_temperature" in input_data:
            features["temperature"] = float(input_data["override_temperature"])
        if "override_humidity" in input_data:
            features["humidity"] = float(input_data["override_humidity"])

    return features


def _post_process_results(
    result: Dict[str, Any], input_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Post-process model results into visualization-ready format.
    """
    risk_score = result.get("risk_score", 0.5)
    risk_tolerance = input_data.get("risk_tolerance", 50)

    # Apply tolerance-adjusted risk level
    risk_level = _get_risk_level(risk_score, risk_tolerance)

    risk_colors = {
        "Low": "#22c55e",
        "Medium": "#f59e0b",
        "High": "#f97316",
        "Extreme": "#ef4444",
    }
    risk_color = risk_colors.get(risk_level, "#f59e0b")

    # Generate temporal forecast
    temporal_forecast = _generate_temporal_forecast(
        risk_score, input_data.get("prediction_hours", 12)
    )

    # Generate fire directions
    wind_dir = input_data.get("wind_direction", 0)
    fire_directions = _calculate_fire_directions(wind_dir, risk_score)

    return {
        "status": result.get("status", "success"),
        "overall_risk": risk_score,
        "risk_level": risk_level,
        "risk_color": risk_color,
        "risk_factors": result.get("factors", {}),
        "confidence": result.get("confidence", 0.5),
        "confidence_interval": result.get("confidence_interval", 0),
        "model_agreement": result.get("model_agreement", 1.0),
        "cnn_probability": result.get("cnn_probability", 0),
        "lgbm_probability": result.get("lgbm_probability", 0),
        "temporal_forecast": temporal_forecast,
        "spread_directions": fire_directions,
        "affected_area": risk_score * 500,  # Simplified estimation
        "max_spread_distance": risk_score * 10,
        "model_type": result.get("model_type", "Model Stacking"),
        "timestamp": result.get("timestamp", datetime.now().isoformat()),
    }


def _generate_temporal_forecast(base_risk: float, hours: int) -> dict:
    """Generate temporal risk forecast.

    Returns:
        Dictionary dengan format yang diharapkan oleh results_display.py:
        - time_steps: list of datetime strings
        - risk_scores: list of risk scores
        - risk_percentages: list of risk percentage estimates (0-100 scale)
    """
    from datetime import timezone

    time_steps = []
    risk_scores = []
    affected_areas = []

    # Configurable time thresholds via environment variables
    PEAK_START = int(os.getenv('TEMPORAL_PEAK_START', '11'))
    PEAK_END = int(os.getenv('TEMPORAL_PEAK_END', '15'))
    NIGHT_END = int(os.getenv('TEMPORAL_NIGHT_END', '6'))
    NIGHT_START = int(os.getenv('TEMPORAL_NIGHT_START', '20'))

    # Guard against invalid hours
    if hours <= 0:
        logger.warning(f"Invalid hours_ahead={hours}, defaulting to 12")
        hours = 12

    current_time = datetime.now(timezone.utc)

    # Guard against NaN input - return uniform forecast
    if np.isnan(base_risk):
        base_risk = 0.0

    for i in range(hours):
        # Add some variation based on time of day
        hour_of_day = (current_time.hour + i) % 24
        time_factor = 1.0

        # Higher risk during midday (configurable peak hours)
        if PEAK_START <= hour_of_day <= PEAK_END:
            time_factor = 1.2
        # Lower risk at night
        elif hour_of_day < NIGHT_END or hour_of_day > NIGHT_START:
            time_factor = 0.8

        hour_risk = base_risk * time_factor
        hour_risk = max(0, min(1, hour_risk))

        time_steps.append((current_time + timedelta(hours=i)).isoformat())
        risk_scores.append(round(float(hour_risk), 4))
        affected_areas.append(round(hour_risk * 100, 1))  # Impact score 0-100

    # Validate list lengths match
    assert len(time_steps) == len(risk_scores) == len(affected_areas), \
        f"List length mismatch: time_steps={len(time_steps)}, risk_scores={len(risk_scores)}, affected_areas={len(affected_areas)}"

    return {
        "time_steps": time_steps,
        "risk_scores": risk_scores,
        "risk_percentages": affected_areas,
    }


def _calculate_fire_directions(wind_dir: float, risk: float) -> list:
    """Calculate potential fire spread directions."""
    directions = []

    # Main direction (wind direction)
    directions.append(
        {
            "direction": wind_dir,
            "angle": wind_dir,
            "speed_kmh": risk * 10,
            "probability": risk,
        }
    )

    # Side directions (±30 degrees)
    for offset in [-30, 30]:
        angle = (wind_dir + offset) % 360
        directions.append(
            {
                "direction": angle,
                "angle": angle,
                "speed_kmh": risk * 7,
                "probability": risk * 0.7,
            }
        )

    # Back direction (opposite to wind, lower probability)
    back_angle = (wind_dir + 180) % 360
    directions.append(
        {
            "direction": back_angle,
            "angle": back_angle,
            "speed_kmh": risk * 3,
            "probability": risk * 0.3,
        }
    )

    return directions


REQUIRED_BATCH_COLUMNS = {
    "latitude",
    "longitude",
    "temperature",
    "humidity",
    "wind_speed",
    "wind_direction",
}
OPTIONAL_BATCH_COLUMNS = {
    "rainfall": 0,
    "vegetation_type": "Savana",
    "fuel_moisture": 35,
    "ndvi": 0.5,
}
RESULT_COLUMNS = [
    "overall_risk",
    "risk_level",
    "confidence",
    "cnn_probability",
    "lgbm_probability",
    "affected_area",
    "max_spread_distance",
    "temporal_forecast",
    "spread_directions",
]


def run_batch_prediction(
    df: pd.DataFrame,
    risk_tolerance: int = 50,
    model_version: Optional[str] = None,
    model_type: str = "new",
    progress_callback: Any | None = None,
) -> pd.DataFrame:
    """Run predictions on every row of a DataFrame.

    Args:
        df: DataFrame containing at least the required columns.
        risk_tolerance: 0-100 risk tolerance from settings.
        model_version: Optional model version string.
        model_type: "new" for Model Stacking, "legacy" for Model Ensemble.
        progress_callback: Optional callable(current, total) for progress UI.

    Returns:
        A copy of *df* with RESULT_COLUMNS appended.  If a row fails,
        the result columns for that row are filled with NaN.
    """
    rows: list[dict] = []
    total = len(df)
    failed_indices = []

    for idx, (_, row) in enumerate(df.iterrows()):
        try:
            input_data = {
                "temperature": float(row.get("temperature", 30)),
                "humidity": float(row.get("humidity", 50)),
                "wind_speed": float(row.get("wind_speed", 5)),
                "wind_direction": float(row.get("wind_direction", 0)),
                "latitude": float(row.get("latitude", -1.1747)),
                "longitude": float(row.get("longitude", 100.4012)),
                "rainfall": float(row.get("rainfall", 0)),
                "vegetation_type": row.get("vegetation_type", "Savana"),
                "fuel_moisture": float(row.get("fuel_moisture", 35)),
                "ndvi": float(row.get("ndvi", 0.5)),
                "risk_tolerance": risk_tolerance,
                "prediction_hours": 12,
                "model_version": model_version,
                "model_type": model_type,
            }
            result = run_prediction(input_data)

            # Build row with only result columns (lat/lon come from original df)
            row_result = {col: result.get(col) for col in RESULT_COLUMNS}
            rows.append(row_result)
        except Exception as e:
            logger.warning(f"Batch row {idx} failed: {e}")
            rows.append({col: None for col in RESULT_COLUMNS})
            failed_indices.append(idx)

        if progress_callback:
            progress_callback(idx + 1, total)

    # Log summary if any failures occurred
    if failed_indices:
        logger.warning(f"Batch prediction failed on {len(failed_indices)}/{total} points. Indices: {failed_indices[:10]}{'...' if len(failed_indices) > 10 else ''}")

    result_df = pd.DataFrame(rows, index=df.index)
    return pd.concat(
        [df.reset_index(drop=True), result_df.reset_index(drop=True)], axis=1
    )


def is_demo_mode() -> bool:
    """Check if prediction engine is running in demo mode."""
    return DEMO_MODE


def get_model_status() -> Dict[str, Any]:
    """Get current model status."""
    active_version = "v0.1.0"
    try:
        from src.models.registry import get_active_model_version

        active = get_active_model_version("cnn") or get_active_model_version("lgbm")
        if active:
            active_version = active.version_string
    except Exception:
        pass

    active_model_type = "new"
    if "active_model_type" in st.session_state:
        active_model_type = st.session_state["active_model_type"]

    if DEMO_MODE:
        model_type_str = "DEMO"
    elif active_model_type == "new":
        model_type_str = "Model Stacking"
    else:
        model_type_str = "Model Ensemble"

    return {
        "demo_mode": DEMO_MODE,
        "model_type": model_type_str,
        "status": "operational",
        "active_version": active_version,
    }


if __name__ == "__main__":
    # Test the prediction engine
    test_input = {
        "temperature": 35,
        "humidity": 40,
        "wind_speed": 8,
        "wind_direction": 90,
        "latitude": -1.1747,
        "longitude": 100.4012,
        "prediction_hours": 12,
    }

    result = run_prediction(test_input)
    print(f"Prediction result: {result}")
