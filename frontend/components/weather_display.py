"""
Weather information display component
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any
import plotly.graph_objects as go
from datetime import datetime, timedelta

try:
    from frontend.utils.theme import PALETTE, RISK_COLORS
except ImportError:
    from utils.theme import PALETTE, RISK_COLORS


def render_weather_info(weather_data: Dict[str, Any]) -> None:
    """Display weather information in an organized layout."""

    # Current weather metrics
    col1, col2, col3, col4 = st.columns(4)

    temp_change = weather_data.get("temp_change", 0)
    humidity_change = weather_data.get("humidity_change", 0)
    wind_change = weather_data.get("wind_change", 0)

    with col1:
        st.metric(
            "🌡️ Suhu",
            f"{weather_data.get('temperature', 0):.1f}°C",
            f"{temp_change:+.1f}°C" if temp_change else None,
        )

    with col2:
        st.metric(
            "💧 Kelembaban",
            f"{weather_data.get('humidity', 0):.0f}%",
            f"{humidity_change:+.0f}%" if humidity_change else None,
        )

    with col3:
        st.metric(
            "💨 Kecepatan Angin",
            f"{weather_data.get('wind_speed', 0):.1f} m/s",
            f"{wind_change:+.1f} m/s" if wind_change else None,
        )

    with col4:
        st.metric(
            "🌧️ Curah Hujan",
            f"{weather_data.get('rainfall', 0):.1f} mm",
            "24 jam",
        )

    # Wind direction visualization
    col_wind1, col_wind2 = st.columns(2)

    with col_wind1:
        st.markdown("**Arah Angin:**")
        wind_dir = weather_data.get("wind_direction", 0)

        # Compass directions — always Indonesian for consistency
        directions = ["U", "BL", "T", "TL", "S", "BD", "B", "BT"]
        angles = [0, 45, 90, 135, 180, 225, 270, 315]

        fig = go.Figure()

        fig.add_trace(
            go.Scatterpolar(
                r=[1, 1, 1, 1, 1, 1, 1, 1],
                theta=angles,
                mode="markers+text",
                text=directions,
                textposition="top center",
                marker=dict(size=15, color="rgba(100,150,200,0.5)"),
            )
        )

        # Wind arrow
        fig.add_trace(
            go.Scatterpolar(
                r=[0, 1],
                theta=[wind_dir, wind_dir],
                mode="lines+markers",
                line=dict(color=RISK_COLORS["tinggi"], width=3),
                marker=dict(size=8, color=RISK_COLORS["tinggi"], symbol="triangle-up"),
                name="Arah Angin",
            )
        )

        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=False, range=[0, 1.3]),
                angularaxis=dict(
                    visible=True,
                    tickfont=dict(size=10, family="'Inter', sans-serif"),
                ),
            ),
            showlegend=False,
            height=300,
            margin=dict(l=40, r=40, t=40, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                size=12,
                color="#64748b"
             ),
         )

        st.plotly_chart(fig, use_container_width=True)

    with col_wind2:
        st.markdown("**Detail Angin:**")

        cardinal = _get_cardinal_direction(wind_dir)
        wind_data = {
            "Arah": f"{wind_dir}° ({cardinal})",
            "Kecepatan": f"{weather_data.get('wind_speed', 0):.1f} m/s",
            "Skala Beaufort": _wind_speed_to_beaufort(
                weather_data.get("wind_speed", 0)
            ),
            "km/j": f"{weather_data.get('wind_speed', 0) * 3.6:.1f} km/j",
        }

        for label, value in wind_data.items():
            st.text(f"{label}: {value}")

        wind_risk = _assess_wind_risk(weather_data.get("wind_speed", 0))
        st.markdown(f"**⚠️ Risiko Angin:** {wind_risk['level']}")
        st.text(wind_risk["description"])

    # Hourly forecast (if available)
    if "hourly_forecast" in weather_data:
        st.markdown("---")
        st.markdown("**Prakiraan 24 Jam:**")

        forecast_df = pd.DataFrame(weather_data["hourly_forecast"])

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            fig_temp = go.Figure()
            fig_temp.add_trace(
                go.Scatter(
                    x=forecast_df["time"],
                    y=forecast_df["temperature"],
                    mode="lines+markers",
                    name="Suhu",
                    line=dict(color=RISK_COLORS["tinggi"], width=2),
                    fill="tozeroy",
                    fillcolor="rgba(239,68,68,0.08)",
                )
            )
            fig_temp.update_layout(
                title="Prediksi Suhu 24 Jam",
                xaxis_title="Waktu",
                yaxis_title="Suhu (°C)",
                height=300,
                hovermode="x unified",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_temp, use_container_width=True)

        with col_chart2:
            fig_humid = go.Figure()
            fig_humid.add_trace(
                go.Scatter(
                    x=forecast_df["time"],
                    y=forecast_df["humidity"],
                    mode="lines+markers",
                    name="Kelembaban",
                    line=dict(color=PALETTE["info"], width=2),
                    fill="tozeroy",
                    fillcolor="rgba(59,130,246,0.08)",
                )
            )
            fig_humid.update_layout(
                title="Prediksi Kelembaban 24 Jam",
                xaxis_title="Waktu",
                yaxis_title="Kelembaban (%)",
                height=300,
                hovermode="x unified",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_humid, use_container_width=True)

    # Weather alerts
    if "alerts" in weather_data:
        st.markdown("---")
        for alert in weather_data["alerts"]:
            alert_type = alert.get("type", "WARNING")
            if alert_type == "CRITICAL":
                st.error(f"🚨 **KRITIS:** {alert['message']}")
            elif alert_type == "WARNING":
                st.warning(f"⚠️ **PERINGATAN:** {alert['message']}")
            else:
                st.info(f"ℹ️ **INFO:** {alert['message']}")


def _get_cardinal_direction(degrees: float) -> str:
    """Convert degrees to cardinal direction (Indonesian)."""
    directions = ["U", "BL", "T", "TL", "S", "BD", "B", "BT"]
    idx = int((degrees + 22.5) / 45) % 8
    return directions[idx]


def _wind_speed_to_beaufort(wind_speed: float) -> str:
    """Convert m/s to Beaufort scale."""
    beaufort_scale = [
        (0, 1, "Tenang"),
        (1, 2, "Sepoi-sepoi"),
        (2, 4, "Lembut"),
        (4, 7, "Sedang"),
        (7, 10, "Cukup Kencang"),
        (10, 12, "Kencang"),
        (12, 15, "Sangat Kencang"),
        (15, 17, "Badai"),
        (17, 25, "Badai Berat"),
    ]

    for min_speed, max_speed, description in beaufort_scale:
        if min_speed <= wind_speed < max_speed:
            return description

    return "Angin Topan"


def _assess_wind_risk(wind_speed: float) -> Dict[str, str]:
    """Assess fire risk based on wind speed."""
    if wind_speed < 2:
        return {
            "level": "🟢 RENDAH",
            "description": "Angin sangat lemah, rambatan api minimal",
        }
    elif wind_speed < 5:
        return {
            "level": "🟡 SEDANG",
            "description": "Angin lemah, rambatan api terkontrol",
        }
    elif wind_speed < 10:
        return {"level": "🟠 TINGGI", "description": "Angin sedang, rambatan api cepat"}
    else:
        return {
            "level": "🔴 SANGAT TINGGI",
            "description": "Angin kencang, api bisa menyebar dengan cepat dan luas",
        }
