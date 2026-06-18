"""
Advanced analysis for AOI batch prediction results.
Provides: risk factors, recommendations, temporal forecast, spread direction.
"""

from typing import Dict, List, Any
import logging
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _calculate_per_point_factors(row: pd.Series) -> Dict[str, float]:
    """Calculate risk contribution for a single point."""
    factors = {}
    # Coerce to numeric with fallback defaults
    temp = pd.to_numeric(row.get("temperature", 30), errors="coerce")
    if pd.isna(temp):
        temp = 30.0
    humidity = pd.to_numeric(row.get("humidity", 50), errors="coerce")
    if pd.isna(humidity):
        humidity = 50.0
    wind = pd.to_numeric(row.get("wind_speed", 5), errors="coerce")
    if pd.isna(wind):
        wind = 5.0
    rainfall = pd.to_numeric(row.get("rainfall", 0), errors="coerce")
    if pd.isna(rainfall):
        rainfall = 0.0

    # Thresholds from environment variables aligned with model training
    temp_threshold = float(os.getenv("RISK_TEMP_THRESHOLD", "32"))
    humidity_threshold = float(os.getenv("RISK_HUMIDITY_THRESHOLD", "40"))
    wind_threshold = float(os.getenv("RISK_WIND_THRESHOLD", "4"))
    rainfall_threshold = float(os.getenv("RISK_RAINFALL_THRESHOLD", "1"))

    # Temperature factor (higher is worse)
    if temp > temp_threshold:
        factors["High Temperature"] = min((temp - temp_threshold) / 10 * 100, 100)

    # Humidity factor (lower is worse)
    if humidity < humidity_threshold:
        factors["Low Humidity"] = (humidity_threshold - humidity) / humidity_threshold * 100

    # Wind factor (higher is worse)
    if wind > wind_threshold:
        factors["Strong Wind"] = min((wind - wind_threshold) / 15 * 100, 100)

    # Rainfall factor (lower is worse)
    if rainfall < rainfall_threshold:
        factors["No Recent Rainfall"] = max(0, 80 * (1 - rainfall / rainfall_threshold))

    return factors


def _rank_risk_factors(batch_df: pd.DataFrame) -> List[Dict[str, float]]:
    """Calculate average risk factor contributions across high-risk points.
    Returns: Dict with feature names as keys, average impact as values."""
    # Filter to High/Extreme
    if "risk_level" in batch_df.columns:
        high_risk_df = batch_df[batch_df["risk_level"].isin(["High", "Extreme"])]
        if len(high_risk_df) == 0:
            high_risk_df = batch_df
    else:
        high_risk_df = batch_df

    if len(high_risk_df) == 0:
        return []

    # Aggregate per-point factors
    factor_sums = {}
    factor_counts = {}

    for _, row in high_risk_df.iterrows():
        point_factors = _calculate_per_point_factors(row)
        for feature, value in point_factors.items():
            factor_sums[feature] = factor_sums.get(feature, 0) + value
            factor_counts[feature] = factor_counts.get(feature, 0) + 1

    # Mean contribution per feature
    avg_factors = {
        feature: round(factor_sums[feature] / factor_counts[feature], 1)
        for feature in factor_sums
    }

    # Sort by contribution descending and return as list for ranking
    sorted_factors = sorted(avg_factors.items(), key=lambda x: x[1], reverse=True)
    return [{"factor": f[0], "pct_high": f[1]} for f in sorted_factors]


def _generate_recommendations(risk_counts: Dict[str, int], total: int) -> List[str]:
    """Generate actionable recommendations."""
    high_pct = (
        ((risk_counts.get("High", 0) + risk_counts.get("Extreme", 0)) / total * 100)
        if total > 0
        else 0
    )
    med_pct = risk_counts.get("Medium", 0) / total * 100 if total > 0 else 0

    recs = []
    if high_pct >= 50:
        recs.append(
            "Alert: **Immediate Action Required**: Deploy firefighting resources."
        )
        recs.append("People: **Evacuation**: Consider evacuating Extreme risk areas.")
        recs.append("Radio: **Monitoring**: Activate 24/7 surveillance.")
    elif high_pct >= 25:
        recs.append("Warning: **Elevated Alert**: Prepare firefighting teams.")
        recs.append("Chart: **Increased Monitoring**: Aerial reconnaissance.")
    else:
        recs.append("Check: **Normal Operations**: Standard monitoring.")

    if med_pct > 30:
        recs.append(
            "Search: **Expand Coverage**: Broaden patrols to Medium-risk areas."
        )
    return recs


def _temporal_forecast(avg_risk: float, hours_ahead: int = 12) -> Dict[str, Any]:
    """
    Generate temporal risk forecast aligned with prediction_engine.
    Returns hourly forecast with diurnal patterns.

    Args:
        avg_risk: Average risk score (0-1)
        hours_ahead: Number of hours to forecast

    Returns:
        Dictionary with time_steps, risk_scores, affected_areas
    """
    from datetime import timezone
    import os

    time_steps = []
    risk_scores = []
    affected_areas = []

    # Configurable time thresholds via environment variables
    PEAK_START = int(os.getenv('TEMPORAL_PEAK_START', '11'))
    PEAK_END = int(os.getenv('TEMPORAL_PEAK_END', '15'))
    NIGHT_END = int(os.getenv('TEMPORAL_NIGHT_END', '6'))
    NIGHT_START = int(os.getenv('TEMPORAL_NIGHT_START', '20'))

    # Guard against invalid hours
    if hours_ahead <= 0:
        logger.warning(f"Invalid hours_ahead={hours_ahead}, defaulting to 12")
        hours_ahead = 12

    current_time = datetime.now()

    # Guard against NaN input - return uniform forecast
    if np.isnan(avg_risk):
        avg_risk = 0.0

    for i in range(hours_ahead):
        hour_of_day = (current_time.hour + i) % 24
        time_factor = 1.0

        # Higher risk during midday (configurable peak hours)
        if PEAK_START <= hour_of_day <= PEAK_END:
            time_factor = 1.2
        # Lower risk at night
        elif hour_of_day < NIGHT_END or hour_of_day > NIGHT_START:
            time_factor = 0.8

        hour_risk = avg_risk * time_factor
        hour_risk = max(0.0, min(1.0, hour_risk))

        time_steps.append((current_time + timedelta(hours=i)).isoformat())
        risk_scores.append(round(float(hour_risk), 4))
        affected_areas.append(round(hour_risk * 100, 1))

    # Validate list lengths match
    assert len(time_steps) == len(risk_scores) == len(affected_areas), \
        f"List length mismatch: time_steps={len(time_steps)}, risk_scores={len(risk_scores)}, affected_areas={len(affected_areas)}"

    return {
        "time_steps": time_steps,
        "risk_scores": risk_scores,
        "risk_percentages": affected_areas,
    }


def _spread_direction(batch_df: pd.DataFrame) -> Dict[str, Any]:
    """Estimate likely spread direction based on weighted wind direction."""
    if "wind_direction" not in batch_df.columns or len(batch_df) == 0:
        return {"direction_deg": None, "direction_cardinal": "N/A", "confidence": 0}

    # Convert to numeric and drop NaNs
    wind_series = pd.to_numeric(batch_df["wind_direction"], errors="coerce").dropna()
    if len(wind_series) == 0 or wind_series.isna().all():
        return {"direction_deg": None, "direction_cardinal": "N/A", "confidence": 0}

    wind_rad = np.deg2rad(wind_series)
    mean_sin = np.mean(np.sin(wind_rad))
    mean_cos = np.mean(np.cos(wind_rad))

    # Risk-weighted direction if available
    if "overall_risk" in batch_df.columns:
        # Align risk weights with valid wind indices
        risk_weights = pd.to_numeric(
            batch_df.loc[wind_series.index, "overall_risk"], errors="coerce"
        ).fillna(0)
        total_weight = np.sum(risk_weights)
        if total_weight > 0:
            w_sin = np.sum(risk_weights * np.sin(wind_rad)) / total_weight
            w_cos = np.sum(risk_weights * np.cos(wind_rad)) / total_weight
            mean_dir_rad = np.arctan2(w_sin, w_cos)
        else:
            mean_dir_rad = np.arctan2(mean_sin, mean_cos)
    else:
        mean_dir_rad = np.arctan2(mean_sin, mean_cos)

    mean_dir_deg = float(np.rad2deg(mean_dir_rad) % 360)

    # Cardinal direction
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    # Handle NaN/inf by defaulting to North
    if not np.isfinite(mean_dir_deg):
        mean_dir_deg = 0.0
    idx = int((mean_dir_deg + 11.25) / 22.5) % 16
    cardinal = dirs[idx]

    # Confidence: circular variance magnitude (0 = scattered, 1 = concentrated)
    confidence = round(float(np.sqrt(mean_sin**2 + mean_cos**2)), 2)

    return {
        "direction_deg": round(mean_dir_deg, 1),
        "direction_cardinal": cardinal,
        "confidence": confidence,
    }


def analyze_aoi_results(
    batch_list: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Main analysis function for AOI batch prediction results."""
    if not batch_list:
        return {}

    # Build DataFrame with proper numeric conversion
    df = pd.DataFrame(batch_list)

    # Ensure numeric columns
    numeric_cols = [
        "overall_risk", "temperature", "humidity", "wind_speed",
        "wind_direction", "rainfall", "fuel_moisture", "ndvi"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    analysis = {}

    # Filter out error entries before computing statistics to avoid distortion
    if "risk_level" in df.columns:
        clean_df = df[df["risk_level"] != "Error"].copy()
    else:
        clean_df = df.copy()

    if len(clean_df) == 0:
        clean_df = df.copy()  # fallback if all entries are errors

    # Compute risk_counts from clean_df for accurate recommendations
    risk_counts = clean_df.groupby("risk_level").size().to_dict() if "risk_level" in clean_df.columns else {}
    analysis["recommendations"] = _generate_recommendations(risk_counts, len(clean_df))

    analysis["risk_factors"] = _rank_risk_factors(df)

    # Guard against NaN mean (e.g., all values are NaN)
    avg_risk_series = clean_df["overall_risk"].dropna()
    avg_risk = float(avg_risk_series.mean()) if not avg_risk_series.empty else 0.0

    analysis["temporal_forecast"] = _temporal_forecast(avg_risk, hours_ahead=12)
    analysis["spread_direction"] = _spread_direction(df)

    high_extreme = (
        ((clean_df["risk_level"] == "High") | (clean_df["risk_level"] == "Extreme")).sum()
        if "risk_level" in clean_df.columns
        else 0
    )

    max_risk = clean_df["overall_risk"].max()
    if pd.isna(max_risk):
        max_risk = 0.0

    analysis["summary"] = {
        "total_points": len(df),
        "high_extreme_pct": round(high_extreme / len(clean_df) * 100, 1)
        if len(clean_df) > 0
        else 0,
        "avg_risk_pct": round(avg_risk * 100, 1),
        "max_risk_pct": round(max_risk * 100, 1),
    }

    return analysis
