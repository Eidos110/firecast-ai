"""
Data handler utility module
"""

from __future__ import annotations

import os
import sys
import json
import logging
import pandas as pd
from typing import Dict, List, Any

import streamlit as st

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "../..", "src"))

logger = logging.getLogger(__name__)


@st.cache_data(ttl=3600, show_spinner=False)
def load_model_features() -> Dict[str, Any]:
    """
    Load model feature names and metadata
    """

    try:
        # Try to load from feature_columns.json
        feature_file = os.path.join(
            os.path.dirname(__file__), "../..", "models", "feature_columns.json"
        )

        if os.path.exists(feature_file):
            with open(feature_file, "r") as f:
                return json.load(f)

    except Exception as e:
        logger.error(f"Error loading features: {e}")

    # Default features if file not found
    return {
        "numeric_features": [
            "temperature",
            "humidity",
            "wind_speed",
            "rainfall",
            "fuel_moisture",
            "latitude",
            "longitude",
        ],
        "categorical_features": ["vegetation_type", "season"],
        "target": "fire_risk",
    }


@st.cache_data(ttl=600, show_spinner=False)
def load_historical_data(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Load historical fire data for analysis
    """

    try:
        data_file = os.path.join(
            os.path.dirname(__file__),
            "../..",
            "data",
            "firecast_data_readymodelling_final_V3.csv",
        )

        if os.path.exists(data_file):
            df = pd.read_csv(data_file)

            # Filter by date range if date column exists
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                start = pd.to_datetime(start_date)
                end = pd.to_datetime(end_date)
                df = df[(df["date"] >= start) & (df["date"] <= end)]

            return df

    except Exception as e:
        logger.error(f"Error loading historical data: {e}")

    return pd.DataFrame()


def get_region_statistics(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Get statistics for a specific region
    """

    # This would typically query a database or load regional data
    # For now, return demo data

    return {
        "region_name": "Riau",
        "total_incidents": 24,
        "avg_area_burned": 125.5,
        "avg_response_time": 2.3,
        "seasonal_risk": {
            "dry_season": 0.85,
            "wet_season": 0.25,
        },
        "vegetation_distribution": {
            "Savana": 30,
            "Hutan Tropis Lembab": 40,
            "Semak Kering": 20,
            "Lahan Gambut": 10,
        },
    }


def validate_input_data(input_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate input data for prediction

    Returns:
        (is_valid, error_message)
    """

    # Check required fields
    required_fields = ["temperature", "humidity", "wind_speed", "wind_direction"]

    for field in required_fields:
        if field not in input_data:
            return False, f"Missing required field: {field}"

    # Validate ranges
    temp = input_data.get("temperature")
    if not (5 <= temp <= 55):
        return False, "Temperature out of valid range (5-55°C)"

    humidity = input_data.get("humidity")
    if not (0 <= humidity <= 100):
        return False, "Humidity out of valid range (0-100%)"

    wind_speed = input_data.get("wind_speed")
    if not (0 <= wind_speed <= 40):
        return False, "Wind speed out of valid range (0-40 m/s)"

    wind_dir = input_data.get("wind_direction")
    if not (0 <= wind_dir <= 360):
        return False, "Wind direction out of valid range (0-360°)"

    return True, ""


def export_prediction_results(
    result: Dict[str, Any], fmt: str = "json", settings: Dict[str, Any] | None = None
) -> str:
    """
    Export prediction results to various formats.

    Args:
        result: Prediction result dictionary.
        fmt: One of "json", "csv", "report".
        settings: Optional dict of active settings (model_type, risk_tolerance, etc.)

    Returns:
        Formatted string ready for download.
    """

    if fmt == "json":
        output = dict(result)
        if settings:
            output["_export_settings"] = settings
        return json.dumps(output, indent=2, default=str)

    elif fmt == "csv":
        # Flatten scalar fields from the result dict
        flat: Dict[str, Any] = {}
        for key, value in result.items():
            if isinstance(value, (dict, list)):
                continue
            flat[key] = value
        # Extract key nested values
        risk_factors = result.get("risk_factors", {})
        for factor, score in risk_factors.items():
            flat[f"factor_{factor}"] = score
        # Add ML metrics
        flat["confidence_interval"] = result.get("confidence_interval", 0)
        flat["model_agreement"] = result.get("model_agreement", 0)
        # Add top SHAP features
        shap_explanation = result.get("shap_explanation", {})
        if shap_explanation and shap_explanation.get("top_features"):
            for i, feature in enumerate(shap_explanation["top_features"][:3], 1):
                prefix = f"shap_{i}_"
                flat[prefix + "feature"] = feature["feature"]
                flat[prefix + "shap_value"] = feature["shap_value"]
                flat[prefix + "contribution"] = feature["contribution"]
        if settings:
            for sk, sv in settings.items():
                flat[f"setting_{sk}"] = sv
        df = pd.DataFrame([flat])
        return df.to_csv(index=False)

    elif fmt == "report":
        return _generate_report_text(result, settings)

    return json.dumps(result, default=str)


def _generate_report_text(
    result: Dict[str, Any], settings: Dict[str, Any] | None = None
) -> str:
    """Generate a human-readable text report from a prediction result."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("FIRE RISK PREDICTION REPORT")
    lines.append("LAPORAN PREDIKSI RISIKO KEBAKARAN")
    lines.append("=" * 60)
    lines.append(f"Timestamp : {result.get('timestamp', 'Unknown')}")
    lines.append(f"Model     : {result.get('model_type', 'Unknown')}")
    lines.append("")

    # Settings used
    if settings:
        lines.append("SETTINGS USED / PENGATURAN:")
        for k, v in settings.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

    overall_risk = result.get("overall_risk", 0)
    risk_level = result.get("risk_level", "Unknown")
    lines.append("PREDICTION RESULTS / HASIL PREDIKSI:")
    lines.append(f"  Overall Risk Score : {overall_risk * 100:.1f}%")
    lines.append(f"  Risk Level         : {risk_level}")
    lines.append(f"  Confidence         : {result.get('confidence', 0) * 100:.1f}%")
    lines.append(
        f"  CNN Probability    : {result.get('cnn_probability', 0) * 100:.1f}%"
    )
    lines.append(
        f"  LightGBM Probability: {result.get('lgbm_probability', 0) * 100:.1f}%"
    )
    lines.append(
        f"  Confidence Interval: {result.get('confidence_interval', 0) * 100:.1f}%"
    )
    lines.append(f"  Model Agreement   : {result.get('model_agreement', 0) * 100:.1f}%")
    lines.append(f"  Affected Area      : {result.get('affected_area', 0):.0f} Ha")
    lines.append(
        f"  Max Spread Distance: {result.get('max_spread_distance', 0):.1f} km"
    )
    lines.append("")

    # Risk factors
    risk_factors = result.get("risk_factors", {})
    if risk_factors:
        lines.append("RISK FACTORS / FAKTOR RISIKO:")
        for factor, score in sorted(
            risk_factors.items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"  - {factor}: {score:.1f}%")
        lines.append("")

    # SHAP explanation
    shap_explanation = result.get("shap_explanation", {})
    if shap_explanation and shap_explanation.get("top_features"):
        lines.append("SHAP FEATURE IMPORTANCE / PENTINGAN FITUR:")
        for feature in shap_explanation["top_features"][:3]:
            contribution = "meningkatkan" if feature["shap_value"] > 0 else "menurunkan"
            lines.append(
                f"  - {feature['feature']}: {feature['shap_value']:.3f} ({contribution} risiko)"
            )
        lines.append("")

    # Temporal forecast summary
    temporal = result.get("temporal_forecast", {})
    if temporal:
        risk_scores = temporal.get("risk_scores", [])
        if risk_scores:
            lines.append("TEMPORAL FORECAST / PREDIKSI TEMPORAL:")
            lines.append(f"  Peak Risk   : {max(risk_scores) * 100:.1f}%")
            lines.append(
                f"  Avg Risk    : {sum(risk_scores) / len(risk_scores) * 100:.1f}%"
            )
            lines.append(f"  Hours Ahead : {len(risk_scores)}")
            lines.append("")

    lines.append("=" * 60)
    lines.append("Generated by FireCast v1.0")
    return "\n".join(lines)


def export_historical_data(df: pd.DataFrame, fmt: str = "csv") -> str | bytes:
    """
    Export a historical-analysis DataFrame to CSV or JSON.

    Args:
        df: DataFrame from analytics functions.
        fmt: "csv" or "json".

    Returns:
        CSV string or JSON string.
    """
    if df is None or df.empty:
        return ""

    if fmt == "csv":
        return df.to_csv(index=False)

    elif fmt == "json":
        # Convert datetime columns to strings for JSON serialisation
        return df.to_json(orient="records", date_format="iso", indent=2)

    return df.to_csv(index=False)
