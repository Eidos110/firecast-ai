"""
Interactive Map Component for Streamlit
Integrates React + Leaflet component for Click-to-Predict & AOI Drawing
"""

import streamlit as st
import streamlit.components.v1 as components
import geopandas as gpd
from shapely.geometry import Point, Polygon, shape
import numpy as np
import json
from datetime import datetime
import logging
import os
import mimetypes

# Ensure JavaScript files are served with correct MIME type
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")

logger = logging.getLogger(__name__)

# Resolve build path relative to this file
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_BUILD_PATH = os.path.abspath(
    os.path.join(_CURRENT_DIR, "..", "..", "frontend_react", "build")
)

logger.info(f"InteractiveMap component build path: {_BUILD_PATH}")
logger.info(f"Checking if build directory exists: {os.path.isdir(_BUILD_PATH)}")
if os.path.isdir(_BUILD_PATH):
    logger.info(f"Build contents: {os.listdir(_BUILD_PATH)}")

InteractiveMap = None
if os.path.isdir(_BUILD_PATH):
    try:
        InteractiveMap = components.declare_component(
            "interactive_map",
            path=_BUILD_PATH,
        )
    except Exception as exc:
        logger.warning("Failed to register interactive_map component: %s", exc)
else:
    logger.warning("Interactive map build directory missing: %s", _BUILD_PATH)


def initialize_session_state():
    """Initialize session state for interactive map."""
    defaults = {
        "map_output": None,
        "prediction_result": None,
        "aoi_geojson": None,
        "last_event_id": None,
        "click_history": [],
        "aoi_history": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_interactive_map(height=600, prediction_overlay=None):
    """
    Render the interactive map component.

    Args:
        height: Map height in pixels
        prediction_overlay: GeoJSON data to overlay on map

    Returns:
        Event data from map interactions
    """
    initialize_session_state()

    if InteractiveMap is None:
        st.warning("Interactive map is unavailable in this deployment because the map component build is missing.")
        return {"type": "placeholder", "lat": None, "lng": None}

    map_output = InteractiveMap(
        height=height,
        predictionOverlay=prediction_overlay,
        key="interactive_map_component",
    )

    return map_output


def handle_map_events(map_output):
    """
    Handle events from the interactive map.

    Args:
        map_output: Event data from map component

    Returns:
        True if event was processed, False otherwise
    """
    if not map_output:
        return False

    event_type = map_output.get("type")
    event_id = map_output.get("event_id")

    # Check for duplicate events
    if event_id and event_id == st.session_state.get("last_event_id"):
        logger.debug(f"Ignoring duplicate event: {event_id}")
        return False

    st.session_state.last_event_id = event_id
    st.session_state.map_output = map_output

    if event_type == "click":
        return handle_click_event(map_output)
    elif event_type == "marker_click":
        # Marker click: also update sidebar coordinates (for selection)
        return handle_click_event(map_output)
    elif event_type == "aoi":
        return handle_aoi_event(map_output)
    elif event_type in ["aoi_updated", "aoi_deleted"]:
        return handle_aoi_update_event(map_output, event_type)

    return False


def handle_click_event(event_data):
    """
    Handle click event from map.

    Args:
        event_data: Click event data

    Returns:
        True if event was processed
    """
    lat = event_data.get("lat")
    lng = event_data.get("lng")
    timestamp = event_data.get("timestamp")

    if lat is None or lng is None:
        return False

    # Store click in history
    click_entry = {
        "lat": lat,
        "lng": lng,
        "timestamp": timestamp,
        "datetime": datetime.fromtimestamp(timestamp / 1000).isoformat()
        if timestamp
        else None,
    }

    st.session_state.click_history.append(click_entry)
    # Keep only last 50 clicks
    if len(st.session_state.click_history) > 50:
        st.session_state.click_history = st.session_state.click_history[-50:]

    logger.info(f"Map click at: ({lat:.4f}, {lng:.4f})")

    # Update selected location (sidebar will read this)
    st.session_state.selected_location = {
        "lat": lat,
        "lon": lng,
        "name": f"Click: {lat:.4f}, {lng:.4f}",
        "zoom": 12,
    }

    return True


def handle_aoi_event(event_data):
    """
    Handle AOI (Area of Interest) drawing event.

    Args:
        event_data: AOI event data with geometry

    Returns:
        True if event was processed
    """
    geometry = event_data.get("geometry")
    timestamp = event_data.get("timestamp")

    if not geometry:
        return False

    # Store AOI in history
    aoi_entry = {
        "geometry": geometry,
        "timestamp": timestamp,
        "datetime": datetime.fromtimestamp(timestamp / 1000).isoformat()
        if timestamp
        else None,
        "type": "created",
    }

    st.session_state.aoi_history.append(aoi_entry)
    st.session_state.aoi_geojson = geometry

    # Log AOI info
    try:
        geom_shape = shape(geometry["geometry"])
        bounds = geom_shape.bounds
        area_km2 = geom_shape.area * 111.32 * 111.32  # Rough approximation
        logger.info(f"AOI drawn: bounds={bounds}, area≈{area_km2:.2f} km²")
    except Exception as e:
        logger.warning(f"Could not calculate AOI properties: {e}")

    return True


def handle_aoi_update_event(event_data, event_type):
    """
    Handle AOI update or delete events.

    Args:
        event_data: Event data with geometries
        event_type: "aoi_updated" or "aoi_deleted"

    Returns:
        True if event was processed
    """
    geometries = event_data.get("geometries", [])
    timestamp = event_data.get("timestamp")

    if not geometries:
        return False

    # Store update in history
    update_entry = {
        "geometries": geometries,
        "timestamp": timestamp,
        "datetime": datetime.fromtimestamp(timestamp / 1000).isoformat()
        if timestamp
        else None,
        "type": event_type,
    }

    st.session_state.aoi_history.append(update_entry)

    if event_type == "aoi_updated" and geometries:
        # Update current AOI with first geometry
        st.session_state.aoi_geojson = geometries[0]
        logger.info(f"AOI updated: {len(geometries)} geometries")
    elif event_type == "aoi_deleted":
        st.session_state.aoi_geojson = None
        logger.info(f"AOI deleted: {len(geometries)} geometries")

    return True


def get_aoi_coordinates():
    """
    Extract coordinates from current AOI.

    Returns:
        List of [lat, lon] coordinates or empty list
    """
    aoi_geojson = st.session_state.get("aoi_geojson")
    if not aoi_geojson:
        return []

    try:
        geom = shape(aoi_geojson["geometry"])
        if geom.geom_type == "Polygon":
            # Extract exterior coordinates
            coords = list(geom.exterior.coords)
            # Convert to [lat, lon] format
            return [[lat, lon] for lon, lat in coords]  # GeoJSON is [lon, lat]
        elif geom.geom_type == "Point":
            # Single point
            lon, lat = geom.coords[0]
            return [[lat, lon]]
    except Exception as e:
        logger.error(f"Error extracting AOI coordinates: {e}")

    return []


def generate_grid_points(aoi_coordinates=None, grid_size=10):
    """
    Generate grid points within AOI polygon (not just bounding box).
    Points are filtered to ensure they lie inside the polygon.

    Args:
        aoi_coordinates: List of [lat, lon] coordinates
        grid_size: Number of points per dimension (grid_size x grid_size)

    Returns:
        List of [lat, lon] grid points inside the AOI polygon.
        May return fewer than grid_size^2 points if polygon is small.
    """
    if not aoi_coordinates:
        aoi_coordinates = get_aoi_coordinates()

    if not aoi_coordinates:
        return []

    lats = [c[0] for c in aoi_coordinates]
    lons = [c[1] for c in aoi_coordinates]

    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Generate a denser grid to have enough points inside polygon
    effective_grid_size = max(grid_size * 3, 30)  # Ensure good coverage
    lat_points = np.linspace(min_lat, max_lat, effective_grid_size)
    lon_points = np.linspace(min_lon, max_lon, effective_grid_size)

    # Create shapely polygon for point-in-polygon test
    polygon = Polygon([(lon, lat) for lat, lon in aoi_coordinates])

    # Filter points inside polygon
    grid_points = []
    for lat in lat_points:
        for lon in lon_points:
            point = Point(lon, lat)
            if polygon.contains(point):
                grid_points.append([lat, lon])
                if len(grid_points) >= grid_size * grid_size:
                    break
        if len(grid_points) >= grid_size * grid_size:
            break

    # If no points found, polygon may be too small or invalid; return empty list
    if len(grid_points) == 0:
        logger.warning("No grid points found inside AOI polygon. "
                      "AOI may be too small or degenerate.")

    return grid_points[:grid_size * grid_size]


def create_prediction_overlay(predictions, format="points"):
    """
    Create GeoJSON overlay for prediction results.

    Args:
        predictions: List of prediction results with lat, lon, risk
        format: "points" or "heatmap"

    Returns:
        GeoJSON data for map overlay
    """
    if not predictions:
        return None

    features = []

    for pred in predictions:
        lat = pred.get("latitude")
        lon = pred.get("longitude")
        risk = pred.get("overall_risk", 0)

        if lat is None or lon is None:
            continue

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],  # GeoJSON uses [lon, lat]
            },
            "properties": {
                "prediction": float(risk),
                "risk_level": pred.get("risk_level", "Unknown"),
                "latitude": float(lat),
                "longitude": float(lon),
                "marker_type": "single" if len(predictions) == 1 else "batch",
            },
        }

        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def get_click_history(limit=10):
    """
    Get recent click history.

    Args:
        limit: Maximum number of clicks to return

    Returns:
        List of recent clicks
    """
    history = st.session_state.get("click_history", [])
    return history[-limit:] if history else []


def get_aoi_history(limit=5):
    """
    Get recent AOI history.

    Args:
        limit: Maximum number of AOI events to return

    Returns:
        List of recent AOI events
    """
    history = st.session_state.get("aoi_history", [])
    return history[-limit:] if history else []


def clear_map_history():
    """Clear map interaction history."""
    st.session_state.click_history = []
    st.session_state.aoi_history = []
    st.session_state.aoi_geojson = None
    st.session_state.map_output = None
    st.session_state.last_event_id = None
