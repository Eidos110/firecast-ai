"""
AOI (Area of Interest) Prediction Module
Handles batch predictions for drawn areas on the interactive map.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging
import math

from .prediction_engine import run_prediction, is_demo_mode, get_model_status
from .gee_data import get_location_data
from ..components.interactive_map import generate_grid_points

logger = logging.getLogger(__name__)


def predict_aoi_grid(
    aoi_coordinates: List[List[float]],
    grid_size: int = 10,
    weather_params: Optional[Dict[str, Any]] = None,
    risk_tolerance: int = 50,
    model_type: str = "new",
) -> Dict[str, Any]:
    """
    Run batch predictions for grid points within an AOI.

    Args:
        aoi_coordinates: List of [lat, lon] coordinates defining the AOI polygon
        grid_size: Number of grid points per dimension (grid_size x grid_size)
        weather_params: Optional weather parameters for all points
        risk_tolerance: Risk tolerance threshold (0-100)
        model_type: Model type to use ("new" or "legacy")

    Returns:
        Dictionary with batch prediction results
    """
    if not aoi_coordinates:
        return {
            "status": "error",
            "message": "No AOI coordinates provided",
            "batch_results": [],
            "grid_count": 0,
        }

    # Validate AOI coordinates (BUG FIX: add validation)
    is_valid, error_msg = validate_aoi_coordinates(aoi_coordinates)
    if not is_valid:
        return {
            "status": "error",
            "message": f"Invalid AOI: {error_msg}",
            "batch_results": [],
            "grid_count": 0,
        }

    # Generate grid points
    grid_points = generate_grid_points(aoi_coordinates, grid_size)

    if not grid_points:
        return {
            "status": "error",
            "message": "Failed to generate grid points",
            "batch_results": [],
            "grid_count": 0,
        }

    logger.info(f"Running AOI batch prediction for {len(grid_points)} grid points")

    # Prepare batch results
    batch_results = []
    high_risk_count = 0
    total_risk = 0

    # Default weather parameters if not provided
    default_weather = weather_params or {
        "temperature": 32,
        "humidity": 45,
        "wind_speed": 5,
        "wind_direction": 180,
        "rainfall": 0,
        "vegetation_type": "Savana",
        "fuel_moisture": 35,
        "ndvi": 0.5,
    }

    # Process each grid point
    for i, (lat, lon) in enumerate(grid_points):
        input_data = {}  # Safe initialization before try block
        try:
            # Prepare input data for this point
            input_data = {
                "latitude": lat,
                "longitude": lon,
                "model_type": model_type,
                "risk_tolerance": risk_tolerance,
                **default_weather,
            }

            # Copy specific weather params if provided
            if weather_params:
                for key in [
                    "temperature",
                    "humidity",
                    "wind_speed",
                    "wind_direction",
                    "rainfall",
                    "vegetation_type",
                    "fuel_moisture",
                    "ndvi",
                ]:
                    if key in weather_params:
                        input_data[key] = weather_params[key]

            # Fetch GEE spatial data for this location (elevation, bands, land cover)
            try:
                gee_data = get_location_data(lat, lon)
                # Merge GEE-derived features
                input_data.update({
                    "elevation": gee_data.get("elevation", 100.0),
                    "B2": gee_data.get("B2", 0.0),
                    "B3": gee_data.get("B3", 0.0),
                    "B4": gee_data.get("B4", 0.0),
                    "B8": gee_data.get("B8", 0.0),
                    "B11": gee_data.get("B11", 0.0),
                    "B12": gee_data.get("B12", 0.0),
                    "land_cover": gee_data.get("land_cover_code", 30),
                })
            except Exception as gee_err:
                logger.warning(f"GEE data fetch failed for point {i} ({lat},{lon}): {gee_err}. Using defaults.")
                # Let prediction fall back to synthetic estimates (unchanged)

            # Run prediction
            result = run_prediction(input_data)

            # Add grid point info and weather parameters
            result["grid_index"] = i
            result["latitude"] = lat
            result["longitude"] = lon
            result["wind_direction"] = input_data.get("wind_direction", 0)
            result["wind_speed"] = input_data.get("wind_speed", 5)
            result["temperature"] = input_data.get("temperature", 32)
            result["humidity"] = input_data.get("humidity", 45)
            result["rainfall"] = input_data.get("rainfall", 0)

            batch_results.append(result)

            # Update statistics
            total_risk += result.get("overall_risk", 0)
            risk_level = result.get("risk_level", "Low")
            if risk_level in ["High", "Extreme"]:
                high_risk_count += 1

        except Exception as e:
            logger.error(f"Error predicting grid point {i} ({lat}, {lon}): {e}")
            # Add error result
            batch_results.append(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "overall_risk": 0,
                    "risk_level": "Error",
                    "confidence": 0,
                    "grid_index": i,
                    "latitude": lat,
                    "longitude": lon,
                    "wind_direction": input_data.get("wind_direction", 0),
                    "wind_speed": input_data.get("wind_speed", 5),
                    "temperature": input_data.get("temperature", 32),
                    "humidity": input_data.get("humidity", 45),
                    "rainfall": input_data.get("rainfall", 0),
                    "error": str(e),
                }
            )

    # Calculate statistics
    avg_risk = total_risk / len(batch_results) if batch_results else 0
    high_risk_percentage = (
        (high_risk_count / len(batch_results)) * 100 if batch_results else 0
    )

    # Determine overall AOI risk level
    # Combine average risk magnitude and percentage of high-risk points
    overall_risk_level = "Low"
    if avg_risk >= 0.7 or high_risk_percentage >= 30:
        overall_risk_level = "High"
    elif avg_risk >= 0.3 or high_risk_percentage >= 10:
        overall_risk_level = "Medium"

    # Calculate AOI center
    lats = [c[0] for c in aoi_coordinates]
    lons = [c[1] for c in aoi_coordinates]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    # Calculate approximate area (in km²)
    area_km2 = _calculate_polygon_area(aoi_coordinates)

    return {
        "status": "success",
        "batch_results": batch_results,
        "grid_count": len(grid_points),
        "aoi_coordinates": aoi_coordinates,
        "aoi_center": [center_lat, center_lon],
        "aoi_area_km2": area_km2,
        "statistics": {
            "average_risk": avg_risk,
            "high_risk_count": high_risk_count,
            "high_risk_percentage": high_risk_percentage,
            "overall_risk_level": overall_risk_level,
            "min_risk": min(
                (r.get("overall_risk", 0) for r in batch_results), default=0
            ),
            "max_risk": max(
                (r.get("overall_risk", 0) for r in batch_results), default=0
            ),
        },
        "timestamp": datetime.now().isoformat(),
        "parameters": {
            "grid_size": grid_size,
            "weather_params": weather_params,
            "risk_tolerance": risk_tolerance,
            "model_type": model_type,
        },
    }


def _calculate_polygon_area(coordinates: List[List[float]]) -> float:
    """
    Calculate area of a polygon on a sphere using the shoelace formula
    on an equal-area cylindrical projection (lon, sin(lat)).

    Args:
        coordinates: List of [lat, lon] points

    Returns:
        Area in square kilometers
    """
    if len(coordinates) < 3:
        return 0.0

    R = 6371.0  # Earth radius in km

    # Use shoelace formula on equal-area cylindrical projection: (lon, sin(lat))
    # This correctly handles spherical geometry for any polygon size/shape
    area = 0.0
    n = len(coordinates)

    for i in range(n):
        j = (i + 1) % n
        # coordinates[i] = [lat, lon]
        lon1 = math.radians(coordinates[i][1])
        lat1 = math.radians(coordinates[i][0])
        lon2 = math.radians(coordinates[j][1])
        lat2 = math.radians(coordinates[j][0])
        # Shoelace on (lon, sin(lat))
        area += lon1 * math.sin(lat2) - lon2 * math.sin(lat1)

    area = abs(area) * R * R / 2.0

    return area


def create_aoi_heatmap_data(batch_results: List[Dict[str, Any]]) -> List[List[float]]:
    """
    Create heatmap data from batch results.

    Args:
        batch_results: List of prediction results

    Returns:
        List of [lat, lon, intensity] for heatmap
    """
    heatmap_data = []

    for result in batch_results:
        lat = result.get("latitude")
        lon = result.get("longitude")
        risk = result.get("overall_risk", 0)

        if lat is not None and lon is not None:
            heatmap_data.append([lat, lon, risk])

    return heatmap_data


def get_aoi_risk_summary(batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary statistics for AOI predictions.
    Handles NaN risk values safely.

    Args:
        batch_results: List of prediction results

    Returns:
        Dictionary with summary statistics
    """
    if not batch_results:
        return {
            "total_points": 0,
            "average_risk": 0,
            "risk_distribution": {},
            "hotspots": [],
        }

    # Calculate risk distribution
    risk_distribution = {"Low": 0, "Medium": 0, "High": 0, "Extreme": 0, "Error": 0}
    valid_risks = []
    hotspots = []

    for result in batch_results:
        risk_level = result.get("risk_level", "Low")
        # Ensure risk_level is one of expected keys
        if risk_level not in risk_distribution:
            risk_distribution[risk_level] = 0
        risk_distribution[risk_level] += 1

        risk = result.get("overall_risk", 0)
        # Only include valid numeric risk values (skip NaN)
        if pd.notna(risk):
            valid_risks.append(float(risk))
            # Identify hotspots (High or Extreme risk with risk > 0.6)
            if risk_level in ["High", "Extreme"] and risk > 0.6:
                hotspots.append(
                    {
                        "latitude": result.get("latitude"),
                        "longitude": result.get("longitude"),
                        "risk": risk,
                        "risk_level": risk_level,
                    }
                )

    total_points = len(batch_results)
    avg_risk = float(np.mean(valid_risks)) if valid_risks else 0.0
    max_risk = float(np.max(valid_risks)) if valid_risks else 0.0

    # Sort hotspots by risk descending
    hotspots.sort(key=lambda x: x["risk"], reverse=True)

    high_extreme = risk_distribution.get("High", 0) + risk_distribution.get("Extreme", 0)

    return {
        "total_points": total_points,
        "average_risk": avg_risk,
        "risk_distribution": risk_distribution,
        "hotspots": hotspots[:10],  # Top 10 hotspots
        "high_risk_count": high_extreme,
        "high_risk_percentage": (high_extreme / total_points * 100) if total_points > 0 else 0,
        "max_risk": max_risk,
    }


def export_aoi_results(aoi_results: Dict[str, Any], format: str = "json") -> str:
    """
    Export AOI prediction results in various formats.

    Args:
        aoi_results: AOI prediction results dictionary
        format: Export format ("json", "csv", "geojson")

    Returns:
        Exported data as string
    """
    if format == "json":
        import json

        return json.dumps(aoi_results, indent=2, default=str)

    elif format == "csv":
        batch_results = aoi_results.get("batch_results", [])
        if not batch_results:
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(batch_results)

        # Select relevant columns
        columns = [
            "latitude",
            "longitude",
            "overall_risk",
            "risk_level",
            "confidence",
            "affected_area",
            "max_spread_distance",
            "grid_index",
        ]

        # Filter available columns
        available_cols = [col for col in columns if col in df.columns]
        df = df[available_cols]

        return df.to_csv(index=False)

    elif format == "geojson":
        import json

        features = []
        batch_results = aoi_results.get("batch_results", [])

        for result in batch_results:
            lat = result.get("latitude")
            lon = result.get("longitude")

            if lat is None or lon is None:
                continue

            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "risk": result.get("overall_risk", 0),
                    "risk_level": result.get("risk_level", "Unknown"),
                    "confidence": result.get("confidence", 0),
                    "grid_index": result.get("grid_index", -1),
                },
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "aoi_statistics": aoi_results.get("statistics", {}),
                "timestamp": aoi_results.get("timestamp", ""),
                "grid_count": aoi_results.get("grid_count", 0),
            },
        }

        return json.dumps(geojson, indent=2)

    else:
        raise ValueError(f"Unsupported export format: {format}")


def validate_aoi_coordinates(coordinates: List[List[float]]) -> Tuple[bool, str]:
    """
    Validate AOI coordinates.

    Args:
        coordinates: List of [lat, lon] coordinates

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not coordinates:
        return False, "No coordinates provided"

    if len(coordinates) < 3:
        return False, "AOI must have at least 3 points"

    # Check latitude range (-90 to 90)
    for lat, lon in coordinates:
        if not (-90 <= lat <= 90):
            return False, f"Invalid latitude: {lat}"
        if not (-180 <= lon <= 180):
            return False, f"Invalid longitude: {lon}"

    # Check for duplicate consecutive points
    for i in range(len(coordinates) - 1):
        if coordinates[i] == coordinates[i + 1]:
            return False, f"Duplicate consecutive points at index {i}"

    # Note: Polygon auto-closure is handled downstream; no mutation here.

    return True, "Valid AOI coordinates"
