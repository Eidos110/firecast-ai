"""
FireCast - Real-Time Fire Risk Prediction System
Main Streamlit Application

This is the main entry point for the FireCast web interface.
"""

import math
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any
import sys
import os
import logging
# NOTE (audit Fase 3b): shapely, generate_grid_points, analyze_aoi_results,
# render_batch_results and _calculate_polygon_area_km2 moved to
# frontend.utils.aoi_controller — they are only used by AOI batch paths.

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directories to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "frontend"))  # Add frontend to path

# Import components
try:
    # Use absolute imports from frontend package
    from frontend.components.sidebar import render_sidebar
    from frontend.components.interactive_map import (
        render_interactive_map,
        handle_map_events,
        create_prediction_overlay,
    )
    from frontend.components.weather_display import render_weather_info
    from frontend.components.results_display import render_results
    from frontend.utils.weather_api import (
        get_weather_data,
        is_demo_mode,
        get_weather_status,
    )
    from frontend.utils.prediction_engine import (
        run_prediction,
        run_batch_prediction,
        is_demo_mode as is_pred_demo_mode,
        get_model_status,
    )
    from frontend.utils.analytics import (
        get_overview_stats,
        get_monthly_fire_data,
        get_seasonal_pattern,
        get_geographic_hotspots,
        get_weather_fire_correlation,
    )
    from frontend.utils.data_handler import (
        export_prediction_results,
        export_historical_data,
    )
    from frontend.utils.i18n import get_text
    from frontend.utils.theme import (
        get_css_variables,
        get_global_font_import,
        RISK_COLORS,
        PALETTE,
        get_risk_level,
        get_risk_color,
        get_risk_icon,
        get_risk_label,
    )
    # Audit Fase 3b: AOI batch logic consolidated into one controller so main()
    # only orchestrates tabs. (Formerly inline blocks in tab1.)
    from frontend.utils.aoi_controller import (
        handle_aoi_event,
        render_aoi_summary_bar,
        render_aoi_results,
        render_aoi_weather_fallback,
    )
except ImportError as e:
    logger.error(f"Failed to import components: {e}")
    # Try relative imports as fallback
    try:
        from components.sidebar import render_sidebar
        from components.interactive_map import (
            render_interactive_map,
            handle_map_events,
            create_prediction_overlay,
        )
        from components.weather_display import render_weather_info
        from components.results_display import render_results
        from utils.weather_api import get_weather_data, is_demo_mode, get_weather_status
        from utils.prediction_engine import (
            run_prediction,
            run_batch_prediction,
            is_demo_mode as is_pred_demo_mode,
            get_model_status,
        )
        from utils.analytics import (
            get_overview_stats,
            get_monthly_fire_data,
            get_seasonal_pattern,
            get_geographic_hotspots,
            get_weather_fire_correlation,
        )
        from utils.data_handler import (
            export_prediction_results,
            export_historical_data,
        )
        from utils.i18n import get_text
        from utils.theme import (
            get_css_variables,
            RISK_COLORS,
            PALETTE,
            get_risk_level,
            get_risk_color,
            get_risk_icon,
            get_risk_label,
        )
        # Audit Fase 3b: AOI batch logic consolidated in one controller.
        from utils.aoi_controller import (
            handle_aoi_event,
            render_aoi_summary_bar,
            render_aoi_results,
            render_aoi_weather_fallback,
        )
    except ImportError as e2:
        logger.error(f"Fallback import also failed: {e2}")
        st.error(f"❌ Failed to load application components: {e}")
        st.stop()

# Page configuration
st.set_page_config(
    page_title="FireCast - Fire Risk Prediction",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject Google Fonts + Custom CSS — design tokens + component styles (Fase 4).
# CSS now lives in frontend/styles/app.css and is injected exactly once per session.
from frontend.styles import inject_design_tokens, render_theme_toggle
inject_design_tokens()
render_theme_toggle()

def initialize_session_state():
    """Initialize all session state variables."""
    defaults = {
        "prediction_result": None,
        "selected_location": {
            "lat": -1.1747,
            "lon": 100.4012,
            "name": "Indonesia (Default)",
            "zoom": 5,
        },
        "location_search_input": "",
        "weather_data": None,
        "is_predicting": False,
        "error_message": None,
        "demo_mode_shown": False,
        "language": "id",
        "last_processed_location": None,
        "last_processed_event_id": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def show_demo_banner():
    """Show demo mode banner if running in demo mode."""
    if is_pred_demo_mode() and not st.session_state.demo_mode_shown:
        st.markdown(
            """
            <div class="demo-banner">
                ⚠️ <strong>DEMO MODE</strong> - Running with simulated data. 
                Configure API keys in .env file for real predictions.
            </div>
        """,
            unsafe_allow_html=True,
        )
        st.session_state.demo_mode_shown = True



def show_api_status():
    """Display API connection status using native Streamlit components."""
    weather_status = get_weather_status()
    model_status = get_model_status()

    cols = st.columns(3)

    with cols[0]:
        if weather_status["openweather_configured"]:
            st.success("Weather API", icon="🌤️")
        else:
            st.warning("Weather (Demo)", icon="🟡")

    with cols[1]:
        if not model_status["demo_mode"]:
            st.success("ML Models", icon="🤖")
        else:
            st.warning("ML (Demo)", icon="🟡")

    with cols[2]:
        st.success("System Ready", icon="✅")


def render_header():
    """Render application header with status indicators."""
    t = _get_translation

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">'
        f'<span style="font-size:2.2rem;">🔥</span>'
        f"<div>"
        f'<h1 style="margin:0;font-size:1.8rem;color:var(--color-text);">FireCast</h1>'
        f'<p style="margin:0;color:var(--color-text-muted);font-size:0.95rem;">{t("app_subtitle")}</p>'
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    show_api_status()


def _get_translation(key: str) -> str:
    """Get translated string in current language."""
    lang = st.session_state.get("language", "id")
    return get_text(key, lang)


def run_fire_prediction(input_data: dict) -> dict:
    """
    Execute fire prediction with proper error handling.

    Args:
        input_data: Dictionary with prediction parameters

    Returns:
        Prediction result dictionary
    """
    try:
        # Read settings from session state
        realtime_weather = st.session_state.get("setting_realtime_weather", True)
        # Use active_model_type from settings or model_management
        model_type = st.session_state.get("active_model_type", "new")
        risk_tolerance = st.session_state.get("setting_risk_tolerance", 50)

        # Pass settings to prediction engine
        input_data["model_type"] = model_type
        input_data["risk_tolerance"] = risk_tolerance

        # Get weather data (only if real-time weather enabled)
        if (
            realtime_weather
            and input_data.get("latitude")
            and input_data.get("longitude")
        ):
            with st.spinner("🌤️ Fetching weather data..."):
                weather = get_weather_data(
                    lat=input_data["latitude"], lon=input_data["longitude"]
                )
                st.session_state.weather_data = weather

                # Add weather data to input
                input_data["temperature"] = weather.get(
                    "temperature", input_data.get("temperature", 30)
                )
                input_data["humidity"] = weather.get(
                    "humidity", input_data.get("humidity", 50)
                )
                input_data["wind_speed"] = weather.get(
                    "wind_speed", input_data.get("wind_speed", 5)
                )
                input_data["wind_direction"] = weather.get(
                    "wind_direction", input_data.get("wind_direction", 0)
                )
                input_data["rainfall"] = weather.get(
                    "rainfall", input_data.get("rainfall", 0)
                )

                # Show weather source
                if is_demo_mode(weather):
                    st.info(
                        "🌤️ Using demo weather data. Configure OPENWEATHER_API_KEY for real data."
                    )
        elif not realtime_weather:
            st.info("⚙️ Real-time weather disabled. Using sidebar values.")

        # Run prediction
        with st.spinner("🧠 Running ML prediction..."):
            result = run_prediction(input_data)

            # Show demo mode warning if applicable
            if result.get("status") == "demo":
                st.warning(
                    "⚠️ Running in DEMO mode with simulated predictions. Configure models for real predictions."
                )

        # Include coordinates for overlay
        result["latitude"] = input_data.get("latitude")
        result["longitude"] = input_data.get("longitude")

        return result

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise


def main():
    """Main application function."""
    # Initialize session state
    initialize_session_state()

    # Show demo banner if applicable
    show_demo_banner()

    # Render header
    render_header()

    st.markdown("---")

    # Create tabs
    t = _get_translation
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            f"🗺️ {t('tab_prediction')}",
            f"📊 {t('tab_analysis')}",
            f"📁 {t('tab_batch')}",
            f"⚙️ {t('tab_settings')}",
        ]
    )

    # Tab 1: Risk Prediction
    with tab1:
        # Single map mode (comparison mode disabled for now)
        col_map, col_sidebar = st.columns([3, 1], gap="large")

        with col_sidebar:
            st.markdown(f"### ⚙️ {t('prediction_params')}")

            try:
                input_data = render_sidebar()
            except Exception as e:
                st.error(f"Sidebar error: {e}")
                input_data = {}

            st.markdown("---")

            is_predicting = st.session_state.get("is_predicting", False)
            predict_disabled = is_predicting

            if st.button(
                f"🚀 {t('run_prediction')}",
                use_container_width=True,
                key="predict_btn",
                disabled=predict_disabled,
            ):
                st.session_state.is_predicting = True
                st.session_state.error_message = None

                try:
                    with st.status("Menjalankan prediksi...", expanded=True) as status:
                        st.write("🌤️ Mengambil data cuaca...")
                        result = run_fire_prediction(input_data)
                        st.session_state.prediction_result = result
                        # Clear any previous AOI analysis (single-point prediction)
                        st.session_state.aoi_analysis = None
                        st.write("✅ Prediksi selesai!")
                        status.update(
                            label="Prediksi berhasil!",
                            state="complete",
                            expanded=False,
                        )
                    st.success(t("prediction_success"))

                except Exception as e:
                    error_msg = f"❌ Prediksi gagal: {str(e)}"
                    st.session_state.error_message = error_msg
                    logger.exception("Prediction error")

                finally:
                    st.session_state.is_predicting = False
                    # No rerun - let Streamlit naturally handle the state

        with col_map:
            st.markdown(f"### 🗺️ {t('interactive_map')}")
            st.caption(
                "💡 Klik peta atau gambar polygon untuk prediksi. Hasil akan ditampilkan di peta."
            )

            # Build GeoJSON overlay from current prediction result
            def build_overlay(pred_result):
                if not pred_result:
                    return None
                if "batch_results" in pred_result:
                    return create_prediction_overlay(pred_result["batch_results"])
                else:
                    lat = pred_result.get("latitude")
                    lon = pred_result.get("longitude")
                    risk = pred_result.get("overall_risk", 0)
                    level = pred_result.get("risk_level", "Low")
                    if lat is not None and lon is not None:
                        return create_prediction_overlay(
                            [
                                {
                                    "latitude": lat,
                                    "longitude": lon,
                                    "overall_risk": risk,
                                    "risk_level": level,
                                }
                            ]
                        )
                    return None

            map_output = {}
            try:
                current_overlay = build_overlay(
                    st.session_state.get("prediction_result")
                )
                map_output = render_interactive_map(
                    height=600, prediction_overlay=current_overlay
                )
            except Exception as e:
                st.error(f"Map error: {e}")
                map_output = {}

        # ── Process interactive map events ─────────────────────────────
        if handle_map_events(map_output):
            event = st.session_state.get("map_output")
            event_id = event.get("event_id") if event else None

            if event and event.get("type") == "click":
                # Check if this click was already processed
                last_processed = st.session_state.get("last_processed_event_id")
                if event_id and event_id != last_processed:
                    st.session_state.last_processed_event_id = event_id
                    # Coordinates are stored in session_state by handle_click_event.
                    # User triggers prediction manually via sidebar button.
                    st.info(
                        "📍 Location selected. Use 'Run Prediction' in the sidebar to compute fire risk."
                    )
            elif event and event.get("type") == "marker_click":
                # Click on a prediction marker
                last_processed = st.session_state.get("last_processed_event_id")
                if event_id and event_id != last_processed:
                    st.session_state.last_processed_event_id = event_id
                    # Coordinates already set by handle_click_event
                    risk = event.get("risk") or 0
                    level = event.get("risk_level") or "Unknown"
                    st.info(
                        f"📍 Point selected — Risk: {risk * 100:.1f}% ({level}). "
                        "Use 'Run Prediction' to recalculate with current settings."
                    )
                    st.rerun()
            elif event and event.get("type") in ["aoi", "aoi_updated", "aoi_deleted"]:
                # Audit Fase 3b: AOI batch logic extracted to aoi_controller
                # so main() only orchestrates tabs. The controller inspects
                # event type, deduplicates by event_id, runs the polygon grid,
                # batch prediction, AOI analysis and session-state wiring.
                # Returns True only when a real prediction was run so we rerun.
                if handle_aoi_event(event, event_id, input_data):
                    st.rerun()

        # ── Floating risk summary (above the fold) ─────────────────
        if st.session_state.prediction_result:
            _result = st.session_state.prediction_result

            # Audit Fase 3b: AOI batch summary bar delegated to the controller.
            # It is a no-op for non-batch results (single-point branch below).
            if "batch_results" in _result:
                render_aoi_summary_bar(_result)
            else:
                # Single prediction result
                _risk = _result.get("overall_risk", 0)
                _level = get_risk_level(_risk)
                _color = get_risk_color(_risk)
                _icon = get_risk_icon(_risk)
                _label = get_risk_label(_risk)
                _area = _result.get("affected_area", 0)

                st.markdown(
                    f"""
                <div class="risk-summary-bar">
                    <span style="font-size:1.4rem;">{_icon}</span>
                    <div>
                        <span style="color:{_color};font-weight:700;font-size:1.1rem;">{_label}</span>
                        <span style="color:var(--color-text-muted);margin-left:8px;">{_risk * 100:.1f}%</span>
                    </div>
                    <span style="color:var(--color-text-muted);font-size:0.85rem;margin-left:auto;">
                        Area: {_area:.0f} Ha
                    </span>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # Display results
        if st.session_state.prediction_result:
            st.markdown("---")
            st.markdown(f"### 📈 {t('prediction_results')}")

            _result = st.session_state.prediction_result

            # Check if this is batch results. Audit Fase 3b: AOI results
            # rendering delegated to the controller (no-op for non-batch).
            if "batch_results" in _result:
                render_aoi_results(_result)
            else:
                # Single prediction result
                try:
                    render_results(st.session_state.prediction_result)
                except Exception as e:
                    st.error(f"Error displaying results: {e}")

            # Export section with format options
            st.markdown(f"#### 📥 {t('export_prediction')}")
            _settings = {
                "model_type": st.session_state.get(
                    "setting_model_type", "Fast (Real-time)"
                ),
                "risk_tolerance": st.session_state.get("setting_risk_tolerance", 50),
                "realtime_weather": st.session_state.get(
                    "setting_realtime_weather", True
                ),
            }
            _result = st.session_state.prediction_result
            _json_data = export_prediction_results(_result, "json", _settings)
            _csv_data = export_prediction_results(_result, "csv", _settings)
            _report_data = export_prediction_results(_result, "report", _settings)
            _ts = _result.get("timestamp", "export").replace(":", "-").split(".")[0]

            dl_col1, dl_col2, dl_col3 = st.columns(3)
            with dl_col1:
                st.download_button(
                    label=f"⬇️ {t('download_json')}",
                    data=_json_data.encode("utf-8"),
                    file_name=f"firecast_prediction_{_ts}.json",
                    mime="application/json",
                    use_container_width=True,
                )
                st.caption("Data lengkap (machine-readable)")
            with dl_col2:
                st.download_button(
                    label=f"⬇️ {t('download_csv')}",
                    data=_csv_data.encode("utf-8"),
                    file_name=f"firecast_prediction_{_ts}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                st.caption("Spreadsheet / Excel")
            with dl_col3:
                st.download_button(
                    label=f"⬇️ {t('download_report')}",
                    data=_report_data.encode("utf-8"),
                    file_name=f"firecast_report_{_ts}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
                st.caption("Laporan teks (human-readable)")

        # Display weather info
        if st.session_state.weather_data:
            st.markdown("---")
            st.markdown(f"### 🌤️ {t('weather_info')}")
            try:
                render_weather_info(st.session_state.weather_data)
            except Exception as e:
                st.error(f"Error displaying weather: {e}")
        elif (
            st.session_state.get("prediction_result")
            and "batch_results" in st.session_state.prediction_result
        ):
            st.markdown("---")
            st.markdown(f"### 🌤️ {t('weather_info')}")
            # Audit Fase 3b: synthetic AOI weather fallback delegated to the
            # controller (no-op when there are no batch_results).
            render_aoi_weather_fallback(st.session_state.prediction_result)

    # Tab 2: Historical Analysis
    with tab2:
        st.markdown(f"### 📊 {t('historical_analysis')}")

        # Load overview stats
        stats = get_overview_stats()

        # Date range info
        st.caption(
            f"Dataset: {stats['date_start']} to {stats['date_end']} | "
            f"{stats['total_records']:,} observations"
        )

        # Overview metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Observations", f"{stats['total_records']:,}")
        with col2:
            st.metric("Fire Events", f"{stats['fire_events']:,}")
        with col3:
            st.metric("Fire Rate", f"{stats['fire_rate']}%")
        with col4:
            st.metric("Unique Locations", f"{stats['unique_locations']:,}")

        st.markdown("---")

        # Monthly fire trend chart
        st.markdown(f"#### 📈 {t('monthly_fire_trend')}")
        monthly = get_monthly_fire_data()
        if not monthly.empty:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(specs=[[{"secondary_y": True}]])

            fig.add_trace(
                go.Bar(
                    x=monthly["date"],
                    y=monthly["fires"],
                    name="Fire Events",
                    marker_color="rgba(239, 68, 68, 0.7)",
                ),
                secondary_y=False,
            )

            fig.add_trace(
                go.Scatter(
                    x=monthly["date"],
                    y=monthly["fire_rate"],
                    name="Fire Rate (%)",
                    mode="lines+markers",
                    line=dict(color="#f59e0b", width=2),
                    marker=dict(size=4),
                ),
                secondary_y=True,
            )

            fig.update_layout(
                height=400,
                hovermode="x unified",
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                ),
                margin=dict(l=20, r=20, t=30, b=20),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            fig.update_yaxes(title_text="Fire Events", secondary_y=False)
            fig.update_yaxes(title_text="Fire Rate (%)", secondary_y=True)
            fig.update_xaxes(showgrid=False)

            st.plotly_chart(fig, use_container_width=True)

        # Two columns: Seasonal pattern + Weather correlation
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("#### 🔥 Seasonal Pattern")
            seasonal = get_seasonal_pattern()
            if not seasonal.empty:
                import plotly.express as px

                fig_seasonal = px.bar(
                    seasonal,
                    x="month_name",
                    y="fire_rate",
                    color="fire_rate",
                    color_continuous_scale="YlOrRd",
                    labels={"fire_rate": "Fire Rate (%)", "month_name": "Month"},
                )
                fig_seasonal.update_layout(
                    height=350,
                    showlegend=False,
                    margin=dict(l=20, r=20, t=10, b=20),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    coloraxis_showscale=False,
                )
                st.plotly_chart(fig_seasonal, use_container_width=True)

        with col_right:
            st.markdown("#### 🌡️ Weather vs Fire")
            corr_data = get_weather_fire_correlation()
            if corr_data and "correlations" in corr_data:
                import plotly.graph_objects as go

                corr = corr_data["correlations"]
                labels = {
                    "temp_max": "Temperature",
                    "wind_speed": "Wind Speed",
                    "precip": "Precipitation",
                    "ndvi": "NDVI",
                    "vpd": "VPD",
                    "fuel_dryness": "Fuel Dryness",
                }

                bar_labels = [labels.get(k, k) for k in corr.keys()]
                bar_values = list(corr.values())
                colors = ["#ef4444" if v > 0 else "#3b82f6" for v in bar_values]

                fig_corr = go.Figure(
                    go.Bar(
                        x=bar_values,
                        y=bar_labels,
                        orientation="h",
                        marker_color=colors,
                        text=[f"{v:.3f}" for v in bar_values],
                        textposition="outside",
                    )
                )
                fig_corr.update_layout(
                    height=350,
                    margin=dict(l=20, r=50, t=10, b=20),
                    xaxis_title="Correlation with Fire",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(range=[-1, 1]),
                )
                st.plotly_chart(fig_corr, use_container_width=True)

        # Geographic hotspots
        st.markdown("#### 📍 Top Fire Hotspots")
        hotspots = get_geographic_hotspots(top_n=10)
        if not hotspots.empty:
            display_cols = ["lat", "lon", "fire_count"]
            rename_map = {
                "lat": "Latitude",
                "lon": "Longitude",
                "fire_count": "Fire Events",
            }
            if "avg_temp_c" in hotspots.columns:
                display_cols.append("avg_temp_c")
                rename_map["avg_temp_c"] = "Avg Temp (°C)"
            if "avg_wind" in hotspots.columns:
                display_cols.append("avg_wind")
                rename_map["avg_wind"] = "Avg Wind (m/s)"

            st.dataframe(
                hotspots[display_cols].rename(columns=rename_map),
                use_container_width=True,
                hide_index=True,
            )

        # Additional stats
        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown(f"**Avg Temperature (fire):** {stats['avg_temp_c']}°C")
        with col_b:
            st.markdown(f"**Avg Wind Speed (fire):** {stats['avg_wind_ms']} m/s")
        with col_c:
            st.markdown(f"**Extreme Weather Events:** {stats['extreme_events']:,}")

        # Historical data export
        st.markdown("---")
        st.markdown("#### 📥 Export Historical Data")
        hcol1, hcol2, hcol3 = st.columns(3)

        with hcol1:
            monthly = get_monthly_fire_data()
            if not monthly.empty:
                st.download_button(
                    label="⬇️ Monthly Fire Data (CSV)",
                    data=export_historical_data(monthly, "csv").encode("utf-8"),
                    file_name="firecast_monthly_fire_data.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        with hcol2:
            hotspots = get_geographic_hotspots(top_n=10)
            if not hotspots.empty:
                st.download_button(
                    label="⬇️ Fire Hotspots (CSV)",
                    data=export_historical_data(hotspots, "csv").encode("utf-8"),
                    file_name="firecast_hotspots.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        with hcol3:
            import json as _json

            stats_json = _json.dumps(stats, indent=2, default=str)
            st.download_button(
                label="⬇️ Overview Stats (JSON)",
                data=stats_json.encode("utf-8"),
                file_name="firecast_overview_stats.json",
                mime="application/json",
                use_container_width=True,
            )

    # Tab 3: Batch Prediction
    with tab3:
        st.markdown(f"### 📁 {t('batch_prediction')}")
        st.caption(t("batch_prediction_desc"))

        # --- CSV template download ---
        import io as _io

        _template_csv = (
            "latitude,longitude,temperature,humidity,wind_speed,wind_direction,rainfall,vegetation_type,fuel_moisture,ndvi\n"
            "-0.5,101.5,34,40,7,180,0,Savana,30,0.45\n"
            "-6.2,106.8,32,55,4,90,2,Hutan Tropis Lembab,50,0.60\n"
            "-2.0,112.0,36,35,10,270,0,Semak Kering,20,0.30\n"
        )
        st.download_button(
            label=f"📄 {t('download_template')}",
            data=_template_csv.encode("utf-8"),
            file_name="firecast_batch_template.csv",
            mime="text/csv",
        )

        st.markdown("---")

        uploaded_csv = st.file_uploader(
            t("choose_csv_file"),
            type=["csv"],
            key="batch_csv_uploader",
            help="Required columns: latitude, longitude, temperature, humidity, wind_speed, wind_direction",
        )

        if uploaded_csv is not None:
            # Validate file size (max 10MB)
            max_size = 10 * 1024 * 1024  # 10MB
            if uploaded_csv.size > max_size:
                st.error(f"❌ File too large ({uploaded_csv.size/1e6:.1f} MB). Maximum size is 10 MB.")
                uploaded_csv = None
                batch_df = pd.DataFrame()
            else:
                # Validate MIME type
                allowed_types = ['text/csv', 'application/vnd.ms-excel', 'application/csv', 'text/plain']
                if uploaded_csv.type not in allowed_types:
                    st.error(f"❌ Invalid file type: {uploaded_csv.type}. Please upload a CSV file.")
                    uploaded_csv = None
                    batch_df = pd.DataFrame()
                else:
                    try:
                        batch_df = pd.read_csv(uploaded_csv)
                    except Exception as e:
                        st.error(f"❌ Failed to read CSV: {e}")
                        batch_df = pd.DataFrame()

            if not batch_df.empty:
                # Validate required columns
                try:
                    from frontend.utils.prediction_engine import (
                        REQUIRED_BATCH_COLUMNS as _req,
                    )
                except ImportError:
                    from utils.prediction_engine import REQUIRED_BATCH_COLUMNS as _req

                csv_cols = set(batch_df.columns.str.lower())
                missing = _req - csv_cols

                if missing:
                    st.error(
                        f"❌ Missing required columns: {', '.join(sorted(missing))}. "
                        f"Required: {', '.join(sorted(_req))}"
                    )
                    st.info(
                        "Tip: Download the CSV template above to see the expected format."
                    )
                else:
                    # Normalize column names to lowercase
                    batch_df.columns = batch_df.columns.str.lower()

                    st.markdown(f"**{len(batch_df)} rows** detected.")
                    st.markdown("**Preview (first 5 rows):**")
                    st.dataframe(
                        batch_df.head(5), use_container_width=True, hide_index=True
                    )

                    if st.button(
                        "🚀 Run Batch Prediction",
                        use_container_width=True,
                        key="batch_predict_btn",
                    ):
                        _tolerance = st.session_state.get("setting_risk_tolerance", 50)

                        progress_bar = st.progress(0, text="Running predictions...")
                        status_text = st.empty()

                        def _update_progress(current, total):
                            pct = current / total if total > 0 else 0
                            progress_bar.progress(
                                pct, text=f"Predicting row {current}/{total}..."
                            )

                        try:
                            import time as _time

                            _t0 = _time.time()

                            result_df = run_batch_prediction(
                                batch_df,
                                risk_tolerance=_tolerance,
                                model_type=st.session_state.get("active_model_type", "new"),
                                progress_callback=_update_progress,
                            )

                            elapsed = _time.time() - _t0
                            progress_bar.progress(1.0, text="Done!")
                            # Check for failures
                            failed_count = (result_df["overall_risk"].isna()).sum()
                            if failed_count > 0:
                                status_text.warning(
                                    f"✅ Batch complete — {len(result_df)} rows in {elapsed:.1f}s. "
                                    f"⚠️ {failed_count} points failed."
                                )
                            else:
                                status_text.success(
                                    f"✅ Batch prediction complete — {len(result_df)} rows in {elapsed:.1f}s"
                                )

                            # --- Summary metrics ---
                            st.markdown("---")
                            st.markdown("#### 📊 Summary")
                            _risk_counts = result_df["risk_level"].value_counts()
                            sm1, sm2, sm3, sm4 = st.columns(4)
                            sm1.metric("Total Rows", len(result_df))
                            sm2.metric("Low", int(_risk_counts.get("Low", 0)))
                            sm3.metric(
                                "High + Extreme",
                                int(
                                    _risk_counts.get("High", 0)
                                    + _risk_counts.get("Extreme", 0)
                                ),
                            )
                            sm4.metric(
                                "Avg Risk",
                                f"{result_df['overall_risk'].mean() * 100:.1f}%",
                            )

                            # --- Results table ---
                            st.markdown("#### 📋 Results")
                            st.dataframe(
                                result_df,
                                use_container_width=True,
                                hide_index=True,
                            )

                            # --- Export buttons ---
                            st.markdown("#### 📥 Export Results")
                            import json as _json

                            _batch_json = result_df.to_json(
                                orient="records", date_format="iso", indent=2
                            )
                            _batch_csv = result_df.to_csv(index=False)

                            # Summary report text
                            _report_lines = [
                                "FIRECAST BATCH PREDICTION REPORT",
                                "=" * 40,
                                f"Total rows : {len(result_df)}",
                                f"Risk tolerance: {_tolerance}",
                                "",
                                "Risk Level Distribution:",
                            ]
                            for level in ["Low", "Medium", "High", "Extreme"]:
                                cnt = int(_risk_counts.get(level, 0))
                                _report_lines.append(f"  {level}: {cnt}")
                            _report_lines.append("")
                            _report_lines.append(
                                f"Avg risk score: {result_df['overall_risk'].mean() * 100:.1f}%"
                            )
                            _report_lines.append(
                                f"Max risk score: {result_df['overall_risk'].max() * 100:.1f}%"
                            )
                            _report_lines.append("=" * 40)
                            _batch_report = "\n".join(_report_lines)

                            bcol1, bcol2, bcol3 = st.columns(3)
                            with bcol1:
                                st.download_button(
                                    label="⬇️ Download CSV",
                                    data=_batch_csv.encode("utf-8"),
                                    file_name="firecast_batch_results.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                )
                            with bcol2:
                                st.download_button(
                                    label="⬇️ Download JSON",
                                    data=_batch_json.encode("utf-8"),
                                    file_name="firecast_batch_results.json",
                                    mime="application/json",
                                    use_container_width=True,
                                )
                            with bcol3:
                                st.download_button(
                                    label="⬇️ Download Report",
                                    data=_batch_report.encode("utf-8"),
                                    file_name="firecast_batch_report.txt",
                                    mime="text/plain",
                                    use_container_width=True,
                                )

                        except Exception as e:
                            progress_bar.empty()
                            status_text.error(f"❌ Batch prediction failed: {e}")
                            logger.exception("Batch prediction error")

    # Tab 4: Settings
    with tab4:
        st.markdown(f"### ⚙️ {t('system_settings')}")

        col_settings1, col_settings2 = st.columns(2)

        with col_settings1:
            st.markdown(f"#### {t('model_config')}")

            current_model = st.session_state.get("active_model_type", "new")
            model_options = ["new", "legacy"]
            model_labels = {
                "new": "Model Stacking",
                "legacy": "Model Ensemble",
            }

            selected = st.radio(
                "Pilih Model ML",
                options=model_options,
                format_func=lambda x: model_labels.get(x, x),
                index=0 if current_model == "new" else 1,
                key="setting_ml_model_type",
                help="Pilih model machine learning untuk prediksi",
            )

            if selected:
                st.session_state["active_model_type"] = selected

            st.slider(
                t("risk_tolerance"),
                min_value=0,
                max_value=100,
                value=st.session_state.get("setting_risk_tolerance", 50),
                help=t("risk_tolerance_help"),
                key="setting_risk_tolerance",
            )

            st.markdown(f"#### {t('data_config')}")
            st.checkbox(
                t("realtime_weather"),
                value=st.session_state.get("setting_realtime_weather", True),
                help=t("realtime_weather_help"),
                key="setting_realtime_weather",
            )
            st.checkbox(
                t("whatif_analysis"),
                value=st.session_state.get("setting_whatif", True),
                help=t("whatif_analysis_help"),
                key="setting_whatif",
            )

            st.markdown(f"#### {t('language_setting')}")
            st.radio(
                t("language"),
                ["Bahasa Indonesia", "English"],
                index=0 if st.session_state.get("language", "id") == "id" else 1,
                key="setting_language",
                horizontal=True,
                on_change=lambda: st.session_state.__setitem__(
                    "language",
                    "id"
                    if st.session_state.setting_language == "Bahasa Indonesia"
                    else "en",
                ),
            )

        with col_settings2:
            st.markdown("#### API Configuration")

            # Show current API status
            weather_status = get_weather_status()
            st.markdown("**Weather API Status:**")
            if weather_status["openweather_configured"]:
                st.success("✅ OpenWeatherMap API configured")
            else:
                st.warning("⚠️ OpenWeatherMap API not configured")
                st.info("Add OPENWEATHER_API_KEY to .env file")

            st.markdown("#### Model Status")
            model_status = get_model_status()
            if model_status["demo_mode"]:
                st.warning("⚠️ Running in Demo Mode")
                st.info(
                    "Models not found or failed to load. Using simulated predictions."
                )
            else:
                st.success(f"✅ {model_status['model_type']} loaded")

    # Footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: gray;'>🔥 FireCast v1.0 - Fire Risk Prediction System</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
