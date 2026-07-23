"""AOI (Area-of-Interest) batch-prediction controller (audit Fase 3b).

All polygon-driven batch prediction logic that previously lived inline in
``frontend/app.py``'s ``main()`` is moved here so ``main()`` only orchestrates
tabs. Concretely:

- ``handle_aoi_event(event, event_id, input_data)`` — runs the polygon grid +
  batch prediction + analysis + session_state update for ``"aoi"`` /
  ``"aoi_updated"`` / ``"aoi_deleted"`` events (former app.py lines ~873-994).
- ``render_aoi_summary_bar(result)``            — floating ``risk-summary-bar``
  for batch results (former app.py lines ~1000-1044).
- ``render_aoi_results(result)``                 — batch results display table
  via ``render_batch_results`` (former app.py lines ~1077-1088).
- ``render_aoi_weather_fallback(result)``       — synthetic weather summary
  built from AOI parameters when no live weather_data is on hand (former
  app.py lines ~1150-1170).
- ``polygon_area_km2(coords)``                    — module-level shoelace
  helper formerly in app.py as ``_calculate_polygon_area_km2``.

Design notes:
- Imports are eager (frontend utils are safe — no torch / shap / sqlmodel here).
- ``streamlit`` is required; this module is only imported from the Streamlit
  app, never from plain Python / API paths.
- Returns booleans from the event handler so the caller can decide whether to
  ``st.rerun()`` (kept in app.py for clarity of control flow).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# AOI-specific external imports (kept local to the controller so app.py stops
# pulling shapely / batch helpers that are only used by AOI paths).
from shapely.geometry import Point, shape

from frontend.components.interactive_map import generate_grid_points
from frontend.components.results_display import render_batch_results
from frontend.components.weather_display import render_weather_info
from frontend.utils.aoi_analysis import analyze_aoi_results
from frontend.utils.prediction_engine import run_batch_prediction

logger = logging.getLogger(__name__)

# Default fall-through values copied verbatim from app.py — keeping the prior
# historical defaults avoids behaviour drift when AOI runs without a sidebar
# value set.
_DEFAULTS: Dict[str, Any] = {
    "temperature": 30,
    "humidity": 50,
    "wind_speed": 5,
    "wind_direction": 0,
    "rainfall": 0,
    "vegetation_type": "Savana",
    "fuel_moisture": 35,
    "ndvi": 0.5,
}

_AOI_EVENTS = ("aoi", "aoi_updated")
_AOI_DELETED_EVENT = "aoi_deleted"


def polygon_area_km2(coords: List[Tuple[float, float]]) -> float:
    """Approximate polygon area in km² via the spherical shoelace formula.

    ``coords`` are ``[lon, lat]`` pairs (shapely ordering). Mirrors the original
    ``_calculate_polygon_area_km2`` that lived module-level in app.py.
    """
    if len(coords) < 3:
        return 0.0
    coords_rad = [(math.radians(lat), math.radians(lon)) for lon, lat in coords]
    area = 0.0
    n = len(coords_rad)
    for i in range(n):
        j = (i + 1) % n
        lat1, lon1 = coords_rad[i]
        lat2, lon2 = coords_rad[j]
        area += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    area = abs(area) * 6371.0**2 / 2.0
    return area


# ────────────────────────────────────────────────────────────────────────────
# Block A: AOI event handler (former app.py lines ~873-994)
# ────────────────────────────────────────────────────────────────────────────

def handle_aoi_event(
    event: Optional[Dict[str, Any]],
    event_id: Optional[str],
    input_data: Dict[str, Any],
) -> bool:
    """Process an AOI-related map event and update ``st.session_state``.

    Handles three event types:
    - ``"aoi"`` / ``"aoi_updated"``: builds grid, filters points inside the
      polygon, runs ``run_batch_prediction``, runs ``analyze_aoi_results`` and
      stores the assembled payload into ``st.session_state.prediction_result``.
    - ``"aoi_deleted"``: clears ``st.session_state.aoi_analysis``.

    Returns ``True`` if a prediction was actually run, so the caller can decide
    whether to ``st.rerun()`` (kept at the call site for clarity of control
    flow). Returns ``False`` for the no-op de-duplicated branch and for
    ``"aoi_deleted"`` (no prediction needs a rerun).

    Side effects:
    - ``st.session_state.last_processed_event_id`` — de-dup token.
    - ``st.session_state.prediction_result``        — full AOI payload.
    - ``st.session_state.aoi_analysis``             — AOI analysis payload.

    Args:
        event:     Result of ``handle_map_events`` / ``map_output``.
        event_id: $client-generated id used as a de-dup token.
        input_data: Sidebar values dict from ``render_sidebar``.
    """
    if not event:
        return False
    etype = event.get("type")

    if etype in _AOI_EVENTS:
        # De-duplicate: skip if we already saw this event_id.
        last_processed = st.session_state.get("last_processed_event_id")
        if event_id and event_id == last_processed:
            return False
        st.session_state.last_processed_event_id = event_id

        aoi_geojson = st.session_state.get("aoi_geojson")
        if not aoi_geojson:
            st.warning("No AOI geometry available")
            return False

        grid_coords = generate_grid_points(grid_size=10)
        if not grid_coords:
            st.warning("No AOI geometry available")
            return False

        geom = (
            aoi_geojson.get("geometry")
            if isinstance(aoi_geojson, dict) and "geometry" in aoi_geojson
            else aoi_geojson
        )
        polygon = shape(geom)

        inside_points = []
        for pt in grid_coords:
            lat, lon = pt
            if polygon.contains(Point(lon, lat)):
                inside_points.append([lat, lon])

        # Fallback: if none inside, use grid centroid.
        if not inside_points:
            lats = [c[0] for c in grid_coords]
            lons = [c[1] for c in grid_coords]
            inside_points = [[sum(lats) / len(lats), sum(lons) / len(lons)]]

        # Build input DataFrame for batch prediction.
        rows = [
            {
                "latitude": lat,
                "longitude": lon,
                "temperature": input_data.get("temperature", _DEFAULTS["temperature"]),
                "humidity": input_data.get("humidity", _DEFAULTS["humidity"]),
                "wind_speed": input_data.get("wind_speed", _DEFAULTS["wind_speed"]),
                "wind_direction": input_data.get("wind_direction", _DEFAULTS["wind_direction"]),
                "rainfall": input_data.get("rainfall", _DEFAULTS["rainfall"]),
                "vegetation_type": input_data.get("vegetation_type", _DEFAULTS["vegetation_type"]),
                "fuel_moisture": input_data.get("fuel_moisture", _DEFAULTS["fuel_moisture"]),
                "ndvi": input_data.get("ndvi", _DEFAULTS["ndvi"]),
            }
            for lat, lon in inside_points
        ]
        batch_df = pd.DataFrame(rows)

        try:
            with st.spinner("🧠 Running AOI batch prediction..."):
                result_df = run_batch_prediction(
                    batch_df,
                    risk_tolerance=st.session_state.get("setting_risk_tolerance", 50),
                    model_type=st.session_state.get("active_model_type", "new"),
                    progress_callback=None,
                )
            batch_list = result_df.to_dict(orient="records")

            aoi_area_km2 = polygon_area_km2(list(polygon.exterior.coords))
            centroid = polygon.centroid
            aoi_center = [centroid.y, centroid.x]  # lat, lon

            st.session_state.prediction_result = {
                "batch_results": batch_list,
                "grid_count": len(batch_list),
                "aoi_area_km2": aoi_area_km2,
                "aoi_center": aoi_center,
                "parameters": {
                    "grid_size": 10,
                    "weather_params": {
                        "temperature": input_data.get("temperature", _DEFAULTS["temperature"]),
                        "humidity": input_data.get("humidity", _DEFAULTS["humidity"]),
                        "wind_speed": input_data.get("wind_speed", _DEFAULTS["wind_speed"]),
                        "wind_direction": input_data.get("wind_direction", _DEFAULTS["wind_direction"]),
                        "rainfall": input_data.get("rainfall", _DEFAULTS["rainfall"]),
                        "vegetation_type": input_data.get("vegetation_type", _DEFAULTS["vegetation_type"]),
                        "fuel_moisture": input_data.get("fuel_moisture", _DEFAULTS["fuel_moisture"]),
                        "ndvi": input_data.get("ndvi", _DEFAULTS["ndvi"]),
                    },
                    "risk_tolerance": st.session_state.get("setting_risk_tolerance", 50),
                    "model_type": st.session_state.get("active_model_type", "new"),
                },
            }

            failed_count = sum(1 for r in batch_list if r.get("overall_risk") is None)
            if failed_count > 0:
                st.warning(
                    f"⚠️ {failed_count} of {len(batch_list)} points failed to "
                    "generate predictions. Check logs for details."
                )

            try:
                analysis = analyze_aoi_results(batch_list)
                st.session_state.aoi_analysis = analysis
            except Exception as e:
                logger.warning(f"AOI analysis failed: {e}")
                st.session_state.aoi_analysis = None

            st.success(f"📐 AOI Batch: {len(batch_list)} points predicted")
            return True

        except Exception as pred_err:
            st.error(f"❌ AOI prediction failed: {pred_err}")
            logger.exception("AOI batch prediction error")
            return False

    if etype == _AOI_DELETED_EVENT:
        st.session_state.aoi_analysis = None
        return False

    return False


# ────────────────────────────────────────────────────────────────────────────
# Block C: floating AOI summary bar (former app.py lines ~1000-1044)
# ────────────────────────────────────────────────────────────────────────────

def render_aoi_summary_bar(result: Dict[str, Any]) -> None:
    """Render the floating ``risk-summary-bar`` strip for a batch result.

    Prefers the AOI analysis ``summary`` when available; otherwise falls back
    to recomputing avg/max/high+extreme counts straight from ``batch_results``.
    Has no effect when the result is not a batch result or has no rows.
    """
    if "batch_results" not in result:
        return
    batch = result.get("batch_results", [])
    grid_count = result.get("grid_count", 0)
    if not batch:
        return

    analysis = st.session_state.get("aoi_analysis")
    if analysis and analysis.get("summary"):
        summ = analysis["summary"]
        avg_risk_pct = summ.get("avg_risk_pct", 0.0)
        max_risk_pct = summ.get("max_risk_pct", 0.0)
        total_points = summ.get("total_points", len(batch))
        high_pct = summ.get("high_extreme_pct", 0.0)
        high_count = round(total_points * high_pct / 100) if total_points > 0 else 0
    else:
        risk_values: List[float] = []
        for r in batch:
            val = r.get("overall_risk", 0)
            try:
                risk_values.append(float(val))
            except (TypeError, ValueError):
                risk_values.append(0.0)
        avg_risk = sum(risk_values) / len(risk_values) if risk_values else 0.0
        avg_risk_pct = avg_risk * 100
        max_risk_pct = max(risk_values) * 100 if risk_values else 0.0
        high_count = sum(
            1 for r in batch if r.get("risk_level") in ("High", "Extreme")
        )

    st.markdown(
        f"""
    <div class="risk-summary-bar">
        <span style="font-size:1.4rem;">📊</span>
        <div>
            <span style="color:#f59e0b;font-weight:700;font-size:1.1rem;">Batch Results</span>
            <span style="color:var(--color-text-muted);margin-left:8px;">{grid_count} points</span>
        </div>
        <span style="color:var(--color-text-muted);font-size:0.85rem;margin-left:auto;">
            Avg: {avg_risk_pct:.1f}% | High/Extreme: {high_count}
        </span>
    </div>
    """,
        unsafe_allow_html=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# Block D: batch results display table (former app.py lines ~1077-1088)
# ────────────────────────────────────────────────────────────────────────────

def render_aoi_results(result: Dict[str, Any]) -> None:
    """Render the rich batch-results visualisation for an AOI prediction.

    No-op when ``result`` is not a batch result or contains no rows. Errors
    from the underlying renderer are surfaced via ``st.error`` so the rest of
    the page can keep rendering.
    """
    if "batch_results" not in result:
        return
    batch = result.get("batch_results", [])
    if not batch:
        return
    try:
        _aoi_analysis = st.session_state.get("aoi_analysis")
        render_batch_results(batch, _aoi_analysis)
    except Exception as e:
        st.error(f"Error displaying batch results: {e}")


# ────────────────────────────────────────────────────────────────────────────
# Block E: AOI-parameter weather fallback (former app.py lines ~1150-1170)
# ────────────────────────────────────────────────────────────────────────────

def render_aoi_weather_fallback(result: Dict[str, Any]) -> None:
    """When no live ``weather_data`` exists but we have AOI batch_results,
    fabricate a synthetic weather summary from AOI input parameters so the
    weather card still renders.

    Caller is responsible for guarding on
    ``not st.session_state.weather_data`` before calling.
    """
    if "batch_results" not in result:
        return
    batch = result.get("batch_results", [])
    if not batch:
        return
    try:
        first_point = batch[0]
        weather_summary = {
            "temperature": first_point.get("temperature", _DEFAULTS["temperature"]),
            "humidity": first_point.get("humidity", _DEFAULTS["humidity"]),
            "wind_speed": first_point.get("wind_speed", _DEFAULTS["wind_speed"]),
            "wind_direction": first_point.get("wind_direction", _DEFAULTS["wind_direction"]),
            "rainfall": first_point.get("rainfall", _DEFAULTS["rainfall"]),
            "source": "AOI Input Parameters",
        }
        render_weather_info(weather_summary)
    except Exception as e:
        st.error(f"Error displaying weather: {e}")
