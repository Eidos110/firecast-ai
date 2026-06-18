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
from shapely.geometry import Point, shape

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
        generate_grid_points,
    )
    from frontend.components.weather_display import render_weather_info
    from frontend.components.results_display import render_results, render_batch_results
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
    from frontend.utils.aoi_analysis import analyze_aoi_results
except ImportError as e:
    logger.error(f"Failed to import components: {e}")
    # Try relative imports as fallback
    try:
        from components.sidebar import render_sidebar
        from components.interactive_map import (
            render_interactive_map,
            handle_map_events,
            create_prediction_overlay,
            generate_grid_points,
        )
        from components.weather_display import render_weather_info
        from components.results_display import render_results, render_batch_results
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
        from utils.aoi_analysis import analyze_aoi_results
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

# Inject Google Fonts + Custom CSS — design tokens + component styles
from frontend.utils.theme import get_global_font_import, get_css_variables
_font_import = get_global_font_import()
_css_vars = get_css_variables()
st.markdown(_font_import, unsafe_allow_html=True)
st.markdown(
    f"""
    <style>
    {_css_vars}

    /* ── Global Typography ─────────────────────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
        font-family: var(--font-primary) !important;
    }}
    
    /* Typography scale for all Streamlit elements */
    .stMarkdown p, .stText {{
        font-size: var(--font-size-base) !important;
        line-height: var(--line-height-normal) !important;
        font-weight: var(--font-weight-normal) !important;
    }}
    
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{
        font-family: var(--font-primary) !important;
        font-weight: var(--font-weight-semibold) !important;
        line-height: var(--line-height-tight) !important;
        margin-top: var(--spacing-lg) !important;
        margin-bottom: var(--spacing-sm) !important;
    }}
    
    .stMarkdown h1 {{ font-size: var(--font-size-3xl) !important; }}
    .stMarkdown h2 {{ font-size: var(--font-size-2xl) !important; }}
    .stMarkdown h3 {{ font-size: var(--font-size-xl) !important; }}
    .stMarkdown h4 {{ font-size: var(--font-size-lg) !important; }}
    
    /* Caption and small text */
    .stMarkdown .stCaption, .stCaption, small, .sim-badge {{
        font-size: var(--font-size-sm) !important;
        line-height: var(--line-height-normal) !important;
    }}
    
    /* Tab labels */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {{
        font-size: var(--font-size-base) !important;
        font-weight: var(--font-weight-medium) !important;
    }}
    
    /* Button text */
    .stButton button, button[kind="secondary"], button[kind="primary"] {{
        font-family: var(--font-primary) !important;
        font-weight: var(--font-weight-medium) !important;
        font-size: var(--font-size-sm) !important;
    }}
    
    /* Selectbox, slider, other inputs labels */
    .stSlider label, .stSelectbox label, .stNumberInput label, .stCheckbox label {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        font-weight: var(--font-weight-medium) !important;
        color: var(--color-text-primary) !important;
    }}
    
    /* Metric labels */
    [data-testid="stMetricLabel"], .stMetricLabel {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        font-weight: var(--font-weight-medium) !important;
        color: var(--color-text-secondary) !important;
    }}
    
    /* Metric value */
    [data-testid="stMetricValue"], .stMetricValue {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-xl) !important;
        font-weight: var(--font-weight-bold) !important;
    }}
    
    .main {{ padding: 0; }}
    
    /* ── Demo banner ────────────────────────────────────────────── */
    .demo-badge, .demo-banner {{
        background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
        color: white;
        padding: 12px 16px;
        border-radius: var(--radius-md);
        text-align: center;
        margin-bottom: var(--spacing-md);
        font-weight: var(--font-weight-semibold);
        font-size: var(--font-size-sm);
        animation: fadeIn 0.4s ease;
    }}

    /* ── API status badges ──────────────────────────────────────── */
    .api-status {{
        font-size: 0.78rem;
        padding: 4px 10px;
        border-radius: var(--radius-full);
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-weight: 500;
    }}
    .api-connected {{
        background: rgba(34, 197, 94, 0.15);
        color: #4ade80;
    }}
    .api-demo {{
        background: rgba(251, 146, 60, 0.15);
        color: #fbbf24;
    }}

    /* ── Risk level blocks ──────────────────────────────────────── */
    .risk-rendah {{
        background: var(--risk-bg-rendah);
        border-left: 4px solid var(--risk-rendah);
        padding: var(--spacing-md);
        border-radius: var(--radius-sm);
    }}
    .risk-sedang {{
        background: var(--risk-bg-sedang);
        border-left: 4px solid var(--risk-sedang);
        padding: var(--spacing-md);
        border-radius: var(--radius-sm);
    }}
    .risk-tinggi {{
        background: var(--risk-bg-tinggi);
        border-left: 4px solid var(--risk-tinggi);
        padding: var(--spacing-md);
        border-radius: var(--radius-sm);
    }}
    .risk-sangat-tinggi {{
        background: var(--risk-bg-sangat-tinggi);
        border-left: 4px solid var(--risk-sangat-tinggi);
        padding: var(--spacing-md);
        border-radius: var(--radius-sm);
    }}

    /* ── Card component ─────────────────────────────────────────── */
    .fc-card {{
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-lg);
        padding: var(--spacing-lg);
        box-shadow: var(--shadow-card);
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }}
    .fc-card:hover {{
        box-shadow: var(--shadow-card-hover);
        transform: translateY(-1px);
    }}

    /* ── Risk score hero card ───────────────────────────────────── */
    .risk-hero {{
        padding: var(--spacing-lg);
        border-radius: var(--radius-lg);
        text-align: center;
        color: white;
        box-shadow: var(--shadow-md);
        animation: fadeIn 0.5s ease;
    }}
    .risk-hero h2 {{
        margin: 0 0 var(--spacing-sm) 0;
        font-size: 1.4rem;
    }}
    .risk-hero .score {{
        font-size: 2.8rem;
        font-weight: 700;
        margin: 0;
        line-height: 1.1;
    }}
    .risk-hero .subtitle {{
        margin-top: var(--spacing-sm);
        opacity: 0.85;
        font-size: 0.9rem;
    }}

    /* Sim-badge (What-If indicator) */
    .sim-badge {{
        display: inline-block;
        background: rgba(251, 146, 60, 0.15);
        color: #fbbf24;
        font-size: var(--font-size-xs) !important;
        padding: 2px 8px;
        border-radius: var(--radius-full);
        font-weight: var(--font-weight-bold) !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        vertical-align: middle;
        margin-bottom: var(--spacing-xs);
    }}
    
    /* Preset button grid spacing */
    [data-testid="stHorizontalBlock"] > div {{
        padding: 0 var(--spacing-xs) !important;
        margin-bottom: var(--spacing-sm) !important;
    }}
    [data-testid="stHorizontalBlock"] > div:first-child {{
        padding-left: 0 !important;
    }}
    [data-testid="stHorizontalBlock"] > div:last-child {{
        padding-right: 0 !important;
    }}
    
    /* Column dividers inside expanders */
    .stExpander [data-testid="stHorizontalBlock"] {{
        margin: var(--spacing-sm) - var(--spacing-md) !important;
    }}
    
    /* Spacer help text under inputs */
    .stSlider [data-baseweb="slider"] > div:nth-child(2) {{
        margin-top: var(--spacing-xs) !important;
        font-size: var(--font-size-xs) !important;
        color: var(--color-text-muted) !important;
    }}

    /* ── Map container ──────────────────────────────────────────── */
    .stfolium-container {{
        width: 100% !important;
        height: 500px !important;
        pointer-events: auto !important;
    }}
    .folium-map {{
        height: 500px !important;
        width: 100% !important;
        pointer-events: auto !important;
    }}
    iframe {{
        border: none !important;
        width: 100% !important;
        height: 500px !important;
        pointer-events: auto !important;
    }}
    
    /* ── Ensure map interactions work ───────────────────────────── */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        pointer-events: auto !important;
    }}
    
    /* ── Sidebar Styling ─────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {{
        background-color: var(--color-surface) !important;
        border-right: 1px solid var(--color-border) !important;
        padding: var(--spacing-sm) var(--spacing-md) !important;
        font-family: var(--font-primary) !important;
    }}
    
    /* Sidebar section headers (expander headers) */
    .stExpander > summary {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-base) !important;
        font-weight: var(--font-weight-semibold) !important;
        color: var(--color-text-primary) !important;
        padding: var(--spacing-sm) var(--spacing-md) !important;
        border-radius: var(--radius-md) !important;
        transition: background 0.15s ease !important;
        margin-top: var(--spacing-xs) !important;
        letter-spacing: -0.01em !important;
    }}
    
    .stExpander > summary:hover {{
        background: rgba(0, 0, 0, 0.03) !important;
    }}
    
    /* Captions and small text */
    .stCaption, .streamlit-expander-header p {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        font-weight: var(--font-weight-normal) !important;
        color: var(--color-text-secondary) !important;
        line-height: var(--line-height-normal) !important;
    }}
    
    /* Expander content padding */
    .stExpander [data-testid="stExpanderDetails"] {{
        padding: var(--spacing-md) !important;
        border: none !important;
        background: transparent !important;
    }}
    
    /* Buttons */
    .stButton button {{
        font-family: var(--font-primary) !important;
        font-weight: var(--font-weight-medium) !important;
        font-size: var(--font-size-sm) !important;
        border-radius: var(--radius-md) !important;
        transition: all 0.15s ease !important;
        border: 1px solid var(--color-border) !important;
        padding: var(--spacing-xs) var(--spacing-sm) !important;
    }}
    
    .stButton button:hover {{
        transform: translateY(-1px) !important;
        box-shadow: var(--shadow-sm) !important;
        border-color: var(--color-accent) !important;
    }}
    
    /* Alert/status messages */
    .stAlert {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        padding: var(--spacing-sm) var(--spacing-md) !important;
        border-radius: var(--radius-md) !important;
        border: none !important;
    }}
    
    [data-baseweb="notification-success"] {{
        background: rgba(34, 197, 94, 0.08) !important;
        border-left: 3px solid var(--color-success) !important;
    }}
    
    [data-baseweb="notification-info"] {{
        background: rgba(59, 130, 246, 0.08) !important;
        border-left: 3px solid var(--color-info) !important;
    }}
    
    [data-baseweb="notification-warning"] {{
        background: rgba(245, 158, 11, 0.08) !important;
        border-left: 3px solid var(--color-warning) !important;
    }}
    
    [data-baseweb="notification-error"] {{
        background: rgba(239, 68, 68, 0.08) !important;
        border-left: 3px solid var(--color-error) !important;
    }}
    
    /* Selectbox */
    .stSelectbox [data-baseweb="select"] {{
        font-family: var(--font-primary) !important;
    }}
    .stSelectbox [data-baseweb="select"] > div {{
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--color-border) !important;
        font-size: var(--font-size-sm) !important;
    }}
    .stSelectbox [data-baseweb="value-container"] {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
    }}
    
    /* Slider */
    .stSlider [data-baseweb="slider"] {{
        margin: var(--spacing-md) 0 !important;
    }}
    .stSlider [data-baseweb="slider"] > div > div > div {{
        background: var(--color-accent) !important;
    }}
    .stSlider label {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        font-weight: var(--font-weight-medium) !important;
        color: var(--color-text-primary) !important;
        margin-bottom: var(--spacing-xs) !important;
    }}
    
    /* Number input */
    .stNumberInput [data-baseweb="input"] {{
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--color-border) !important;
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
    }}
    
    /* Metric widget */
    .stMetricLabel, [data-testid="stMetricLabel"] {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        font-weight: var(--font-weight-medium) !important;
        color: var(--color-text-secondary) !important;
        letter-spacing: 0.01em !important;
    }}
    .stMetricValue, [data-testid="stMetricValue"] {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-xl) !important;
        font-weight: var(--font-weight-bold) !important;
        color: var(--color-text-primary) !important;
    }}
    
    /* Divider */
    hr, [data-testid="stMarkdownContainer"] hr {{
        margin: var(--spacing-lg) 0 !important;
        border: none !important;
        border-top: 1px solid var(--color-border) !important;
    }}
    
     /* Sidebar section title (h3 used in sidebar) */
     h3, .stMarkdown h3 {{
         font-family: var(--font-primary) !important;
         font-size: var(--font-size-base) !important;
         font-weight: var(--font-weight-semibold) !important;
         color: var(--color-text-primary) !important;
         margin: var(--spacing-md) 0 var(--spacing-sm) 0 !important;
         letter-spacing: -0.01em !important;
         line-height: var(--line-height-tight) !important;
     }}
    
    /* Checkbox */
    .stCheckbox label {{
        font-family: var(--font-primary) !important;
        font-size: var(--font-size-sm) !important;
        font-weight: var(--font-weight-medium) !important;
    }}

    /* ── Responsive adjustments ─────────────────────────────────── */
    @media (max-width: 768px) {{
        .risk-hero .score {{ font-size: 2rem; }}
        .fc-card {{ padding: var(--spacing-md); }}
        iframe, .folium-map, .stfolium-container {{ height: 350px !important; }}
    }}
    </style>
""",
    unsafe_allow_html=True,
)

def _calculate_polygon_area_km2(coords: list) -> float:
    """Calculate approximate area of a polygon (lat/lon list) in km² using shoelace formula."""
    if len(coords) < 3:
        return 0.0
    # Convert to radians: coords are [lon, lat] from shapely
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
        "last_processed_aoi": None,
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
                    risk = event.get("risk", 0)
                    level = event.get("risk_level", "Unknown")
                    st.info(
                        f"📍 Point selected — Risk: {risk * 100:.1f}% ({level}). "
                        "Use 'Run Prediction' to recalculate with current settings."
                    )
                    st.rerun()
            elif event and event.get("type") in ["aoi", "aoi_updated"]:
                # Prevent duplicate batch runs (same event_id)
                last_processed = st.session_state.get("last_processed_event_id")
                if event_id and event_id == last_processed:
                    pass
                else:
                    st.session_state.last_processed_event_id = event_id
                    aoi_geojson = st.session_state.get("aoi_geojson")
                    if aoi_geojson:
                        grid_coords = generate_grid_points(grid_size=10)
                        if grid_coords:
                            # Extract geometry
                            geom = (
                                aoi_geojson.get("geometry")
                                if isinstance(aoi_geojson, dict) and "geometry" in aoi_geojson
                                else aoi_geojson
                            )
                            polygon = shape(geom)

                            # Find points inside polygon
                            inside_points = []
                            for pt in grid_coords:
                                lat, lon = pt
                                if polygon.contains(Point(lon, lat)):
                                    inside_points.append([lat, lon])

                            # Fallback: if none inside, use grid centroid
                            if not inside_points:
                                lats = [c[0] for c in grid_coords]
                                lons = [c[1] for c in grid_coords]
                                inside_points = [
                                    [sum(lats) / len(lats), sum(lons) / len(lons)]
                                ]

                            # Build input DataFrame for batch prediction
                            rows = []
                            for lat, lon in inside_points:
                                rows.append(
                                    {
                                        "latitude": lat,
                                        "longitude": lon,
                                        "temperature": input_data.get("temperature", 30),
                                        "humidity": input_data.get("humidity", 50),
                                        "wind_speed": input_data.get("wind_speed", 5),
                                        "wind_direction": input_data.get("wind_direction", 0),
                                        "rainfall": input_data.get("rainfall", 0),
                                        "vegetation_type": input_data.get("vegetation_type", "Savana"),
                                        "fuel_moisture": input_data.get("fuel_moisture", 35),
                                        "ndvi": input_data.get("ndvi", 0.5),
                                    }
                                )
                            batch_df = pd.DataFrame(rows)

                            # Run batch prediction with error handling
                            try:
                                with st.spinner("🧠 Running AOI batch prediction..."):
                                    result_df = run_batch_prediction(
                                        batch_df,
                                        risk_tolerance=st.session_state.get("setting_risk_tolerance", 50),
                                        model_type=st.session_state.get("active_model_type", "new"),
                                        progress_callback=None,
                                    )
                                batch_list = result_df.to_dict(orient="records")

                                # Compute AOI metadata
                                aoi_area_km2 = _calculate_polygon_area_km2(list(polygon.exterior.coords))
                                centroid = polygon.centroid
                                aoi_center = [centroid.y, centroid.x]  # lat, lon

                                # Store full AOI metadata + batch results
                                st.session_state.prediction_result = {
                                    "batch_results": batch_list,
                                    "grid_count": len(batch_list),
                                    "aoi_area_km2": aoi_area_km2,
                                    "aoi_center": aoi_center,
                                    "parameters": {
                                        "grid_size": 10,
                                        "weather_params": {
                                            "temperature": input_data.get("temperature", 30),
                                            "humidity": input_data.get("humidity", 50),
                                            "wind_speed": input_data.get("wind_speed", 5),
                                            "wind_direction": input_data.get("wind_direction", 0),
                                            "rainfall": input_data.get("rainfall", 0),
                                            "vegetation_type": input_data.get("vegetation_type", "Savana"),
                                            "fuel_moisture": input_data.get("fuel_moisture", 35),
                                            "ndvi": input_data.get("ndvi", 0.5),
                                        },
                                        "risk_tolerance": st.session_state.get("setting_risk_tolerance", 50),
                                        "model_type": st.session_state.get("active_model_type", "new"),
                                    },
                                }

                                # Check for failed predictions
                                failed_count = sum(1 for r in batch_list if r.get("overall_risk") is None)
                                if failed_count > 0:
                                    st.warning(
                                        f"⚠️ {failed_count} of {len(batch_list)} points failed to generate predictions. "
                                        "Check logs for details."
                                    )

                                # Run advanced analysis on batch results
                                try:
                                    analysis = analyze_aoi_results(batch_list)
                                    st.session_state.aoi_analysis = analysis
                                except Exception as e:
                                    logger.warning(f"AOI analysis failed: {e}")
                                    st.session_state.aoi_analysis = None

                                st.success(
                                    f"📐 AOI Batch: {len(batch_list)} points predicted"
                                )
                                st.rerun()

                            except Exception as pred_err:
                                st.error(f"❌ AOI prediction failed: {pred_err}")
                                logger.exception("AOI batch prediction error")
                    else:
                        st.warning("No AOI geometry available")

            elif event and event.get("type") == "aoi_deleted":
                # Clear analysis when AOI is deleted
                st.session_state.aoi_analysis = None

        # ── Floating risk summary (above the fold) ─────────────────
        if st.session_state.prediction_result:
            _result = st.session_state.prediction_result

            # Check if this is batch results
            if "batch_results" in _result:
                _batch = _result.get("batch_results", [])
                _grid_count = _result.get("grid_count", 0)
                if _batch:
                    # Use analysis summary if available, otherwise compute from batch
                    _aoi_analysis = st.session_state.get("aoi_analysis")
                    if _aoi_analysis and _aoi_analysis.get("summary"):
                        summ = _aoi_analysis["summary"]
                        _avg_risk_pct = summ.get("avg_risk_pct", 0.0)
                        _max_risk_pct = summ.get("max_risk_pct", 0.0)
                        # Compute high+extreme count from summary's total_points and percentage
                        _total_points = summ.get("total_points", len(_batch))
                        _high_pct = summ.get("high_extreme_pct", 0.0)
                        _high_count = round(_total_points * _high_pct / 100) if _total_points > 0 else 0
                    else:
                        # Fallback: calculate from raw batch_results
                        _risk_values = []
                        for r in _batch:
                            val = r.get("overall_risk", 0)
                            try:
                                _risk_values.append(float(val))
                            except (TypeError, ValueError):
                                _risk_values.append(0.0)
                        _avg_risk = sum(_risk_values) / len(_risk_values) if _risk_values else 0.0
                        _avg_risk_pct = _avg_risk * 100
                        _max_risk_pct = max(_risk_values) * 100 if _risk_values else 0.0
                        _high_count = sum(
                            1 for r in _batch if r.get("risk_level") in ["High", "Extreme"]
                        )
                    st.markdown(
                        f"""
                    <div class="risk-summary-bar">
                        <span style="font-size:1.4rem;">📊</span>
                        <div>
                            <span style="color:#f59e0b;font-weight:700;font-size:1.1rem;">Batch Results</span>
                            <span style="color:var(--color-text-muted);margin-left:8px;">{_grid_count} points</span>
                        </div>
                        <span style="color:var(--color-text-muted);font-size:0.85rem;margin-left:auto;">
                            Avg: {_avg_risk_pct:.1f}% | High/Extreme: {_high_count}
                        </span>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
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

            # Check if this is batch results
            if "batch_results" in _result:
                # Display batch results with rich visualizations
                try:
                    _batch = _result.get("batch_results", [])
                    _grid_count = _result.get("grid_count", 0)
                    if _batch:
                        # Get AOI analysis if available
                        _aoi_analysis = st.session_state.get("aoi_analysis")
                        render_batch_results(_batch, _aoi_analysis)
                except Exception as e:
                    st.error(f"Error displaying batch results: {e}")
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
            try:
                _batch = st.session_state.prediction_result.get("batch_results", [])
                if _batch and len(_batch) > 0:
                    _first_point = _batch[0]
                    _weather_summary = {
                        "temperature": _first_point.get("temperature", 30),
                        "humidity": _first_point.get("humidity", 50),
                        "wind_speed": _first_point.get("wind_speed", 5),
                        "wind_direction": _first_point.get("wind_direction", 0),
                        "rainfall": _first_point.get("rainfall", 0),
                        "source": "AOI Input Parameters",
                    }
                    render_weather_info(_weather_summary)
            except Exception as e:
                st.error(f"Error displaying weather: {e}")

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
