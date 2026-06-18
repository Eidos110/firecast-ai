"""
Interactive map component - visualization only with manual input
"""

import streamlit as st
import numpy as np
from typing import Dict, Tuple
import math
import logging

# Import folium
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MarkerCluster, Draw

logger = logging.getLogger(__name__)


def add_risk_visualization(
    m: folium.Map, prediction_data: dict, center_lat: float, center_lon: float
) -> folium.Map:
    """
    Add risk visualization markers (circle + marker) for single point predictions.
    """
    risk = prediction_data.get("overall_risk", 0)
    risk_level = prediction_data.get("risk_level", "Unknown")
    risk_color = prediction_data.get("risk_color", "#f59e0b")

    # Map risk color names to folium Icon colors
    color_map = {
        "#22c55e": "green",
        "#f59e0b": "orange",
        "#ef4444": "red",
        "#991b1b": "darkred",
    }
    icon_color = color_map.get(risk_color, "orange")

    # Circle zone - radius based on risk level
    radius_m = 2000 + (risk * 15000)
    folium.Circle(
        location=[center_lat, center_lon],
        radius=radius_m,
        color=risk_color,
        fill=True,
        fillOpacity=0.25,
        weight=2,
        popup=f"<b>Risk Level: {risk_level}</b><br>Risk Score: {risk * 100:.1f}%",
    ).add_to(m)

    # Marker with fire icon
    folium.Marker(
        location=[center_lat, center_lon],
        icon=folium.Icon(color=icon_color, icon="fire", prefix="fa"),
        popup=f"<b>🔥 Prediksi Kebakaran</b><br>Risiko: {risk * 100:.1f}%<br>Level: {risk_level}",
        tooltip=f"Risk: {risk_level}",
    ).add_to(m)

    return m


def extract_aoi_coordinates(all_drawings: dict) -> list:
    """
    Extract coordinates from drawn AOI shapes.
    Returns list of coordinate pairs [[lat, lon], ...]
    """
    if not all_drawings or "features" not in all_drawings:
        return []

    coordinates = []
    for feature in all_drawings.get("features", []):
        geometry = feature.get("geometry", {})
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates", [])

        if geom_type == "Point":
            coordinates.append([coords[1], coords[0]])
        elif geom_type in ("Polygon", "Rectangle"):
            if coords and len(coords) > 0:
                ring = coords[0]
                coordinates.extend([[c[1], c[0]] for c in ring[:-1]])
        elif geom_type == "Circle":
            if len(coords) >= 2:
                coordinates.append([coords[1], coords[0]])

    return coordinates


def generate_grid_points(aoi_coordinates: list, grid_size: int = 5) -> list:
    """
    Generate grid points within AOI bounding box (5x5 = 25 points).
    """
    if not aoi_coordinates:
        return []

    lats = [c[0] for c in aoi_coordinates]
    lons = [c[1] for c in aoi_coordinates]

    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    lat_step = (max_lat - min_lat) / (grid_size - 1) if grid_size > 1 else 0
    lon_step = (max_lon - min_lon) / (grid_size - 1) if grid_size > 1 else 0

    grid_points = []
    for i in range(grid_size):
        for j in range(grid_size):
            lat = min_lat + i * lat_step
            lon = min_lon + j * lon_step
            grid_points.append([lat, lon])

    return grid_points


def render_map(prediction_data: dict = None, map_key: str = None) -> Dict:
    """
    Render map for visualization only.
    Manual coordinate input is used for prediction.
    """

    try:
        # Get location from session state
        location = st.session_state.get(
            "selected_location",
            {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia", "zoom": 5},
        )

        center_lat = location.get("lat", -1.1747)
        center_lon = location.get("lon", 100.4012)

        return _render_folium_map(prediction_data, center_lat, center_lon)

    except Exception as e:
        st.error(f"Map error: {str(e)}")
        logger.error(f"Map render error: {e}")
        return {}


def _render_folium_map(
    prediction_data: dict,
    center_lat: float,
    center_lon: float,
) -> Dict:
    """Render map for visualization only."""

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    # Add marker
    folium.Marker(
        location=[center_lat, center_lon],
        popup="Selected Location",
    ).add_to(m)

    # Add prediction overlay if available
    if prediction_data:
        _build_prediction_fg(m, prediction_data)

    # Render map
    st_folium(m, width="100%", height=400)

    return {}


def _build_prediction_fg(m: folium.Map, prediction_data: dict) -> None:
    """
    Build prediction overlay directly on the map (not in FeatureGroup).
    """
    risk_color_map = {
        "Low": ("#22c55e", "green"),
        "Medium": ("#f59e0b", "orange"),
        "High": ("#ef4444", "red"),
        "Extreme": ("#991b1b", "darkred"),
    }

    # Single point prediction result
    if prediction_data.get("overall_risk") is not None:
        lat = prediction_data.get("latitude", -1.1747)
        lon = prediction_data.get("longitude", 100.4012)
        risk = prediction_data.get("overall_risk", 0)
        risk_level = prediction_data.get("risk_level", "Medium")
        hex_color, icon_color = risk_color_map.get(risk_level, ("#f59e0b", "orange"))

        folium.Circle(
            location=[lat, lon],
            radius=2000 + risk * 15000,
            color=hex_color,
            fill=True,
            fill_opacity=0.25,
            weight=2,
            popup=f"<b>Risk: {risk_level}</b><br>{risk * 100:.1f}%",
        ).add_to(m)

        folium.Marker(
            location=[lat, lon],
            icon=folium.Icon(color=icon_color, icon="fire", prefix="fa"),
            popup=f"<b>🔥 {risk_level}</b><br>{risk * 100:.1f}%",
            tooltip=f"Risk: {risk_level} ({risk * 100:.1f}%)",
        ).add_to(m)

    # Batch prediction results (AOI grid)
    if "batch_results" in prediction_data:
        for result in prediction_data.get("batch_results", []):
            lat = result.get("latitude")
            lon = result.get("longitude")
            risk = result.get("overall_risk", 0)
            risk_level = result.get("risk_level", "Medium")
            if lat is None or lon is None:
                continue
            hex_color, icon_color = risk_color_map.get(
                risk_level, ("#f59e0b", "orange")
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=8 + risk * 12,
                color=hex_color,
                fill=True,
                fill_opacity=0.7,
                weight=2,
                popup=f"<b>{risk_level}</b><br>{risk * 100:.1f}%<br>{lat:.4f},{lon:.4f}",
                tooltip=f"{risk_level}: {risk * 100:.1f}%",
            ).add_to(m)

        # Draw AOI boundary
        aoi_coords = prediction_data.get("aoi_coordinates", [])
        if aoi_coords and len(aoi_coords) > 2:
            folium.Polygon(
                locations=aoi_coords + [aoi_coords[0]],
                color="#3b82f6",
                fill=True,
                fill_opacity=0.08,
                weight=2,
                popup="AOI Boundary",
                dash_array="5,5",
            ).add_to(m)


def _generate_sample_heatmap_data(center_lat: float, center_lon: float) -> list:
    """
    Generate deterministic sample heatmap data for risk visualization.
    Uses a seeded RNG so the map is stable across reruns.
    Format: [[lat, lon, intensity], ...]
    """

    rng = np.random.RandomState(42)
    sample_points = []

    # Create a cluster of points around the center location
    for _ in range(15):
        lat_offset = rng.uniform(-0.5, 0.5)
        lon_offset = rng.uniform(-0.5, 0.5)
        intensity = rng.uniform(0.3, 0.95)

        sample_points.append(
            [center_lat + lat_offset, center_lon + lon_offset, intensity]
        )

    # Known hotspots
    hotspots = [
        [-0.5, 101.5, 0.9],
        [-0.4, 101.6, 0.85],
        [-1.0, 112.0, 0.8],
        [-1.1, 112.1, 0.75],
    ]

    sample_points.extend(hotspots)
    return sample_points


def _add_sample_markers(marker_cluster) -> None:
    """
    Add sample fire incident markers to map
    """

    incidents = [
        {
            "location": [-0.45, 101.55],
            "name": "Kebakaran Riau",
            "date": "2026-03-10",
            "area": "150 Ha",
            "severity": "TINGGI",
        },
        {
            "location": [-1.05, 112.05],
            "name": "Kebakaran Kalimantan",
            "date": "2026-03-08",
            "area": "320 Ha",
            "severity": "SANGAT TINGGI",
        },
        {
            "location": [-3.45, 103.55],
            "name": "Kebakaran Sumsel",
            "date": "2026-03-05",
            "area": "85 Ha",
            "severity": "SEDANG",
        },
    ]

    for incident in incidents:
        color_map = {
            "RENDAH": "green",
            "SEDANG": "orange",
            "TINGGI": "red",
            "SANGAT TINGGI": "darkred",
        }

        popup_text = f"""
        <b>{incident["name"]}</b><br>
        📅 {incident["date"]}<br>
        📏 Area: {incident["area"]}<br>
        ⚠️ Keparahan: {incident["severity"]}<br>
        """

        folium.Marker(
            location=incident["location"],
            popup=folium.Popup(popup_text, max_width=250),
            icon=folium.Icon(
                color=color_map.get(incident["severity"], "blue"),
                icon="fire",
                prefix="fa",
            ),
        ).add_to(marker_cluster)


def add_prediction_overlay(m: folium.Map, prediction_data: dict) -> folium.Map:
    """
    Add prediction results as overlay on map
    """

    # Add risk visualization markers for single point predictions
    if prediction_data.get("overall_risk") is not None:
        center_lat = prediction_data.get("latitude", -1.1747)
        center_lon = prediction_data.get("longitude", 100.4012)
        add_risk_visualization(m, prediction_data, center_lat, center_lon)

    # Add batch results visualization (grid points)
    if "batch_results" in prediction_data:
        batch_results = prediction_data.get("batch_results", [])
        if batch_results:
            # Add markers for each grid point
            for result in batch_results:
                lat = result.get("latitude")
                lon = result.get("longitude")
                risk = result.get("overall_risk", 0)
                risk_level = result.get("risk_level", "Unknown")

                if lat and lon:
                    # Map risk level to color
                    color_map = {
                        "Low": "green",
                        "Medium": "orange",
                        "High": "red",
                        "Extreme": "darkred",
                    }
                    color = color_map.get(risk_level, "orange")

                    # Add marker
                    folium.Marker(
                        location=[lat, lon],
                        icon=folium.Icon(color=color, icon="fire", prefix="fa"),
                        popup=f"<b>🔥 Risk: {risk_level}</b><br>Score: {risk * 100:.1f}%<br>Lat: {lat:.4f}<br>Lon: {lon:.4f}",
                        tooltip=f"{risk_level}: {risk * 100:.1f}%",
                    ).add_to(m)

                    # Add circle for risk zone
                    radius_m = 1000 + (risk * 8000)
                    risk_color = color_map.get(risk_level, "#f59e0b")
                    folium.Circle(
                        location=[lat, lon],
                        radius=radius_m,
                        color=risk_color,
                        fill=True,
                        fillOpacity=0.2,
                        weight=1,
                    ).add_to(m)

            # If we have AOI coordinates, draw the boundary
            if "aoi_coordinates" in prediction_data:
                aoi_coords = prediction_data.get("aoi_coordinates", [])
                if aoi_coords:
                    # Close the polygon
                    closed_coords = (
                        aoi_coords + [aoi_coords[0]]
                        if len(aoi_coords) > 2
                        else aoi_coords
                    )
                    folium.Polygon(
                        locations=closed_coords,
                        color="#3b82f6",
                        fill=True,
                        fillOpacity=0.1,
                        weight=2,
                        popup="AOI Boundary",
                    ).add_to(m)

    # Add risk zones as polygons (if provided in expected format)
    if "risk_zones" in prediction_data:
        # Add risk zones as polygons
        for zone in prediction_data["risk_zones"]:
            folium.Polygon(
                locations=zone["coordinates"],
                color=zone["color"],
                fill=True,
                fillOpacity=0.4,
                weight=2,
                popup=zone["label"],
            ).add_to(m)

    # Add directional arrows showing fire propagation (if provided in expected format)
    if "fire_direction" in prediction_data:
        for arrow in prediction_data["fire_direction"]:
            folium.PolyLine(
                locations=arrow["path"],
                color=arrow["color"],
                weight=3,
                opacity=0.8,
                popup=f"Probabilitas: {arrow['probability'] * 100:.1f}%",
            ).add_to(m)

    # Handle FireCast prediction format (spread_directions)
    if "spread_directions" in prediction_data:
        # Convert spread_directions to map arrows
        center_lat = prediction_data.get("latitude", -1.1747)
        center_lon = prediction_data.get("longitude", 100.4012)

        for direction_info in prediction_data["spread_directions"]:
            angle = direction_info.get("angle", 0)
            speed_kmh = direction_info.get("speed_kmh", 5)
            probability = direction_info.get("probability", 0.5)

            # Calculate arrow path (simple line in direction of spread)
            # Convert angle to radians
            angle_rad = math.radians(angle)

            # Calculate end point based on speed and probability
            distance_km = speed_kmh * probability * 2  # Scale for visibility
            # Rough conversion: 1 degree ≈ 111 km at equator
            lat_offset = (distance_km * math.cos(angle_rad)) / 111.0
            lon_offset = (distance_km * math.sin(angle_rad)) / (
                111.0 * math.cos(math.radians(center_lat))
            )

            # Create arrow path
            path = [
                [center_lat, center_lon],
                [center_lat + lat_offset, center_lon + lon_offset],
            ]

            # Determine color based on probability
            if probability >= 0.7:
                color = "red"
            elif probability >= 0.4:
                color = "orange"
            else:
                color = "yellow"

            folium.PolyLine(
                locations=path,
                color=color,
                weight=3,
                opacity=0.8,
                popup=f"Probabilitas: {probability * 100:.1f}%<br>Kecepatan: {speed_kmh:.1f} km/h<br>Arah: {angle:.0f}°",
            ).add_to(m)

    # Handle affected area visualization (temporal forecast)
    if "temporal_forecast" in prediction_data:
        temporal_data = prediction_data["temporal_forecast"]
        if "time_steps" in temporal_data and "risk_percentages" in temporal_data:
            # Show the maximum affected area as a circle
            max_area_ha = (
                max(temporal_data["risk_percentages"])
                if temporal_data["risk_percentages"]
                else 0
            )
            if max_area_ha > 0:
                # Convert hectares to radius in kilometers (rough approximation)
                # 1 ha = 0.01 km², so radius = sqrt(area/pi)
                radius_km = math.sqrt(max_area_ha * 0.01 / math.pi)
                # Convert to degrees (rough approximation)
                radius_deg = radius_km / 111.0

                # Create circle points
                circle_points = []
                num_points = 32
                for i in range(num_points):
                    angle = 2 * math.pi * i / num_points if num_points > 0 else 0
                    lat_offset = radius_deg * math.cos(angle)
                    lon_offset = (
                        radius_deg
                        * math.sin(angle)
                        / math.cos(math.radians(center_lat))
                    )
                    circle_points.append(
                        [center_lat + lat_offset, center_lon + lon_offset]
                    )

                # Add the circle
                folium.Polygon(
                    locations=circle_points,
                    color="red",
                    fill=True,
                    fillOpacity=0.2,
                    weight=2,
                    popup=f"Area Terdampak Maksimal: {max_area_ha:.0f} Ha",
                ).add_to(m)

    return m
