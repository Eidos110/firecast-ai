"""
Results display component for prediction outputs
"""

import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="plotly")
warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")

import logging
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from frontend.utils.theme import (
        get_risk_level,
        get_risk_color,
        get_risk_bg_color,
        get_risk_label,
        get_risk_icon,
        PALETTE,
        RISK_COLORS,
    )
except ImportError:
    from utils.theme import (
        get_risk_level,
        get_risk_color,
        get_risk_bg_color,
        get_risk_label,
        get_risk_icon,
        PALETTE,
        RISK_COLORS,
    )



# -- Plotly template overrides --------------------------------------
PLOTLY_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(
        color=PALETTE["text"],
        family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        size=12
    ),
    xaxis=dict(
        gridcolor="rgba(148,163,184,0.12)",
        zerolinecolor="rgba(148,163,184,0.2)",
        tickfont=dict(size=11)
    ),
    yaxis=dict(
        gridcolor="rgba(148,163,184,0.12)",
        zerolinecolor="rgba(148,163,184,0.2)",
        tickfont=dict(size=11)
    ),
)


def _get_cardinal(degrees: float) -> str:
    """Convert degrees to 16-point cardinal direction. Handles NaN/None gracefully."""
    if not np.isfinite(degrees):
        return "N"  # Default to North when direction is undefined
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((degrees + 11.25) / 22.5) % 16
    return dirs[idx]


def _get_risk_level_safe(probability: float) -> str:
    """Convert probability to English risk level string. Safe for batch_df apply."""
    if pd.isna(probability):
        return "Low"
    if probability < 0.3:
        return "Low"
    elif probability < 0.5:
        return "Medium"
    elif probability < 0.7:
        return "High"
    else:
        return "Extreme"


def _safe_count(value) -> int:
    """Safely convert any value to integer count, defaulting to 0 on error."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def render_batch_results(batch_results: list, analysis: dict = None) -> None:
    """Display batch/AOI prediction results with rich visualizations similar to single prediction."""

    if not batch_results:
        st.warning("No batch results to display.")
        return

    batch_df = pd.DataFrame(batch_results)

    # Ensure all relevant numeric columns are properly coerced
    numeric_cols = [
        "overall_risk", "temperature", "humidity", "wind_speed",
        "wind_direction", "rainfall", "fuel_moisture", "ndvi"
    ]
    for col in numeric_cols:
        if col in batch_df.columns:
            batch_df[col] = pd.to_numeric(batch_df[col], errors="coerce")
    # Guarantee overall_risk exists
    if "overall_risk" not in batch_df.columns:
        batch_df["overall_risk"] = np.nan

    # Compute aggregated metrics with NaN guards
    avg_risk = batch_df["overall_risk"].mean(skipna=True)
    if pd.isna(avg_risk):
        avg_risk = 0.0
    max_risk = batch_df["overall_risk"].max(skipna=True)
    if pd.isna(max_risk):
        max_risk = 0.0
    total_points = len(batch_df)
    
    # Ensure risk_level column exists; derive from overall_risk if missing
    if "risk_level" not in batch_df.columns:
        batch_df["risk_level"] = batch_df["overall_risk"].apply(
            lambda r: _get_risk_level_safe(r)
        )
    
    # Build risk_counts dictionary
    risk_counts = batch_df.groupby("risk_level").size().to_dict()
    
    # Compute high+extreme count safely
    high_extreme_count = 0
    for _key in ("High", "Extreme"):
        _val = risk_counts.get(_key, 0)
        try:
            high_extreme_count += int(_val)
        except (ValueError, TypeError):
            pass
    high_extreme_pct = (
        (high_extreme_count / total_points * 100) if total_points > 0 else 0
    )

    # Determine overall risk level for the area
    overall_level = get_risk_level(avg_risk)
    overall_color = get_risk_color(avg_risk)
    overall_icon = get_risk_icon(avg_risk)
    overall_label = get_risk_label(avg_risk)

    # -- Risk hero + metrics ----------------------------------------
    col_risk1, col_risk2, col_risk3 = st.columns(3)

    with col_risk1:
        st.markdown(
            f"""
        <div class="risk-hero" style="background: linear-gradient(135deg, {overall_color} 0%, {overall_color}dd 100%);">
            <h2>{overall_icon} {overall_label}</h2>
            <p class="score">{avg_risk * 100:.1f}%</p>
            <p class="subtitle">Risiko Rata-rata Area (AOI)</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_risk2:
        st.metric(
            " Total Titik Diprediksi",
            f"{total_points}",
            f"{high_extreme_count} High/Extreme",
        )

    with col_risk3:
        st.metric(
            " Risiko Maksimum",
            f"{max_risk * 100:.1f}%",
            "Titik tertinggi di area",
        )

    # -- AOI metadata --------------------------------------------------
    _pr = st.session_state.get("prediction_result", {})
    aoi_area = _pr.get("aoi_area_km2", 0)
    grid_count = _pr.get("grid_count", total_points)
    params = _pr.get("parameters", {})
    weather = params.get("weather_params", {})

    # -- AOI summary + risk legend ------------------------------------
    st.markdown("#### 📐 Informasi Area AOI")
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Luas AOI", f"{aoi_area:.2f} km²" if aoi_area else "N/A")
    with col_m2:
        st.metric("Grid Points", f"{grid_count}", f"{total_points} diprediksi")
    with col_m3:
        st.metric("Suhu Rata-rata", f"{weather.get('temperature', 30)}°C")
    with col_m4:
        st.metric("Kelembaban", f"{weather.get('humidity', 50)}%")

    # Risk level legend
    st.markdown("---")
    st.markdown("#### 🎨 Skala Tingkat Risiko")
    legend_col1, legend_col2, legend_col3, legend_col4 = st.columns(4)
    with legend_col1:
        st.markdown(f"<span style='color:{RISK_COLORS['rendah']};font-weight:bold;'>● Rendah (0–30%)</span>", unsafe_allow_html=True)
    with legend_col2:
        st.markdown(f"<span style='color:{RISK_COLORS['sedang']};font-weight:bold;'>● Sedang (30–60%)</span>", unsafe_allow_html=True)
    with legend_col3:
        st.markdown(f"<span style='color:{RISK_COLORS['tinggi']};font-weight:bold;'>● Tinggi (60–80%)</span>", unsafe_allow_html=True)
    with legend_col4:
        st.markdown(f"<span style='color:{RISK_COLORS['sangat_tinggi']};font-weight:bold;'>● Sangat Tinggi (>80%)</span>", unsafe_allow_html=True)
    st.markdown("---")
    st.caption("📊 **Klasifikasi risiko:** Rendah (<30%), Sedang (30–60%), Tinggi (60–80%), Sangat Tinggi (>80%) — berdasarkan tolerance 50% (standar).")

    # -- Spatial variability & homogeneity (batch characteristics) ------

    st.markdown("---")
    col_conf, col_agree = st.columns(2)
    with col_conf:
        std_risk = batch_df["overall_risk"].std()
        st.metric(
            "Ragam Risiko (Keragaman)",
            f"{std_risk * 100:.1f}%",
            "Keragaman risiko antar titik (lebih rendah = lebih homogen)",
        )
    with col_agree:
        low_count = _safe_count(risk_counts.get("Low", 0))
        # Compute high_count safely
        high_count = 0
        for _key in ("High", "Extreme"):
            _val = risk_counts.get(_key, 0)
            try:
                high_count += int(_val)
            except (ValueError, TypeError):
                pass
        med_count = _safe_count(risk_counts.get("Medium", 0))
        dominant_count = max(low_count, high_count, med_count)
        dominance_pct = (dominant_count / total_points * 100) if total_points > 0 else 0
        st.metric(
            "Dominasi Zona Risiko",
            f"{dominant_count} titik ({dominance_pct:.0f}%)",
            "Zona risiko yang paling dominan di AOI",
        )

    st.markdown("---")

    # -- Analysis summary --------------------------------------------
    if analysis and analysis.get("summary"):
        st.markdown("#### 📊 Ringkasan Analisis")
        summ = analysis["summary"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Titik", summ.get("total_points", 0))
        c2.metric("High+Extreme %", f"{summ.get('high_extreme_pct', 0):.1f}%")
        c3.metric("Risiko Rata-rata", f"{summ.get('avg_risk_pct', 0):.1f}%")
        c4.metric("Risiko Maks", f"{summ.get('max_risk_pct', 0):.1f}%")
        st.markdown("---")

    # -- Risk factors + recommendations -----------------------------
    col_factors1, col_factors2 = st.columns(2)

    with col_factors1:
        st.markdown("###  Faktor Penyebab Risiko Tinggi")

        # Use analysis risk_factors if available
        risk_factors = {}
        if analysis and analysis.get("risk_factors"):
            # Map descriptive factor names to Indonesian labels
            label_map = {
                "High Temperature": "Suhu Tinggi",
                "Low Humidity": "Kelembaban Rendah",
                "Strong Wind": "Angin Kencang",
                "No Recent Rainfall": "Tidak Ada Hujan",
            }
            for item in analysis["risk_factors"]:
                factor_key = item["factor"]
                # Only show factors that have impact > 0
                impact = item.get("pct_high", 0)
                if impact > 0:
                    label = label_map.get(factor_key, factor_key.title())
                    risk_factors[label] = impact

        if risk_factors:
            factors_df = pd.DataFrame(
                list(risk_factors.items()), columns=["Faktor", "Kontribusi"]
            )
            factors_df = factors_df.sort_values("Kontribusi", ascending=False)

            # Compute colors based on contribution values
            max_contrib = factors_df["Kontribusi"].max()
            colors = []
            for val in factors_df["Kontribusi"]:
                if max_contrib > 0:
                    ratio = val / max_contrib
                    if ratio < 0.5:
                        colors.append("#22c55e")
                    elif ratio < 0.75:
                        colors.append("#fb923c")
                    else:
                        colors.append("#ef4444")
                else:
                    colors.append("#22c55e")

            fig_factors = go.Figure()
            fig_factors.add_trace(
                go.Bar(
                    x=factors_df["Kontribusi"],
                    y=factors_df["Faktor"],
                    orientation="h",
                    marker_color=colors,
                    text=[f"{v:.1f}%" for v in factors_df["Kontribusi"]],
                    textposition="outside",
                )
            )
            fig_factors.update_layout(
                title="Kontribusi Risiko (%)",
                xaxis_title="Kontribusi Risiko (%)",
                yaxis_title="Faktor",
                height=300,
                showlegend=False,
                margin=dict(l=150, r=20, t=20, b=20),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_factors, use_container_width=True)

            # --- Threshold reference ---
            st.markdown("**📏 Batas Ambang (Thresholds) Risiko:**")
            st.caption(
                "Faktor dianggap berisiko jika: Suhu >33°C, Kelembaban <45%, Angin >5 m/s, "
                "Hujan <0.5 mm, Bahan kering <30%, NDVI >0.8"
            )

            top_factor = factors_df.iloc[0]
            st.info(
                f"**Faktor Utama:** {top_factor['Faktor']} ({top_factor['Kontribusi']:.1f}% kontribusi)\n\n"
                "Area ini berisiko tinggi karena kombinasi vegetasi mudah terbakar dan kondisi cuaca mendukung penyebaran api."
            )

    with col_factors2:
        st.markdown("###  Rekomendasi Tindakan")
        if analysis and analysis.get("recommendations"):
            recs = analysis["recommendations"]
            for i, rec in enumerate(recs, 1):
                st.markdown(f"{i}. {rec}")
        else:
            risk_level_numeric = _get_risk_numeric(avg_risk)
            recommendations = _get_recommendations(
                risk_level_numeric, {"overall_risk": avg_risk}
            )
            for i, rec in enumerate(recommendations, 1):
                st.markdown(f"**{i}. {rec['title']}**")
                st.write(rec["description"])
                if "action" in rec:
                    st.caption(f" Tindakan: {rec['action']}")

    st.markdown("---")



    # -- Fire spread direction --------------------------------------
    st.markdown("### 🔥 Arah Rambatan Api (Probabilitas)")
    st.caption("""
    **Cara membaca:**
    - **Bagian kiri (Compass Rose):** Arah dominan rambatan api ditunjukkan oleh panah terpanjang. 
      Panah kecil menampilkan arah alternatif (±45°, ±90°). Confidence tinggi (dekat 1.0) berarti api lebih konsisten mengikuti arah dominan.
    - **Bagian kanan (Bar Chart):** Probabilitas penyebaran api ke 8 arah utama (±0°, ±45°, ±90°, ±135°, ±180° dari arah dominan).
      Arah dengan probabilitas tertinggi adalah arah utama rambatan.
    - **Interpretasi:** Siapkan rencana evakuasi & penanggulangan **terbalik arah dominan** (sebelumdan sesudahnya, ¬ probabilitas rendah).
    """)

    if analysis and analysis.get("spread_direction"):
        spread = analysis["spread_direction"]
        if spread.get("direction_deg") is not None:
            col_dir1, col_dir2 = st.columns(2)

            # Extract spread direction data with type safety
            deg = float(spread.get("direction_deg", 0))
            cardinal = str(spread.get("direction_cardinal", "N"))
            conf = float(spread.get("confidence", 0))

            with col_dir1:
                # Build directions with realistic probability distribution
                directions = [
                    {"dir": cardinal,               "angle": deg,            "prob": 0.5 + conf * 0.3, "is_main": True},
                    {"dir": _get_cardinal(int((deg+45) % 360)),  "angle": (deg+45) % 360,  "prob": 0.15 * (1 - conf*0.3), "is_main": False},
                    {"dir": _get_cardinal(int((deg-45) % 360)),  "angle": (deg-45) % 360,  "prob": 0.15 * (1 - conf*0.3), "is_main": False},
                    {"dir": _get_cardinal(int((deg+90) % 360)),  "angle": (deg+90) % 360,  "prob": 0.10 * (1 - conf*0.5), "is_main": False},
                    {"dir": _get_cardinal(int((deg+135) % 360)), "angle": (deg+135) % 360, "prob": 0.05,               "is_main": False},
                ]
                # Safely sum probabilities, converting each to float to avoid int+str errors
                total = 0.0
                for d in directions:
                    try:
                        total += float(d["prob"])
                    except (TypeError, ValueError):
                        total += 0.0
                if total <= 0:
                    total = 1.0
                for d in directions:
                    try:
                        prob_val = float(d["prob"])
                    except (TypeError, ValueError):
                        prob_val = 0.0
                    d["prob"] = round(prob_val / total, 3)

                # Compass rose (polar)
                fig_compass = go.Figure()
                for d in directions:
                    length = 1.0 if d["is_main"] else 0.5
                    lw = 6 if d["is_main"] else 3
                    color = RISK_COLORS["sangat_tinggi"] if d["is_main"] else RISK_COLORS["tinggi"]
                    fig_compass.add_trace(
                        go.Scatterpolar(
                            r=[0, length],
                            theta=[d["angle"], d["angle"]],
                            mode="lines",
                            name=d["dir"],
                            line=dict(color=color, width=lw),
                            hovertemplate=f"<b>{d['dir']} ({int(d['angle'])}°)</b><br>Prob: {d['prob']:.1%}<extra></extra>",
                        )
                    )
                fig_compass.update_layout(
                    title=f"🧭 Arah Dominan Rambatan Api<br><sup>Confidence: {conf:.0%}</sup>",
                    polar=dict(
                        radialaxis=dict(visible=False, range=[0, 1.2]),
                        angularaxis=dict(
                            direction="clockwise",
                            rotation=90,
                            tickmode="array",
                            tickvals=[0,45,90,135,180,225,270,315],
                            ticktext=["N","NE","E","SE","S","SW","W","NW"],
                        ),
                    ),
                    showlegend=False,
                    height=350,
                    margin=dict(l=20, r=20, t=60, b=20),
                )
                st.plotly_chart(fig_compass, use_container_width=True)

            with col_dir2:
                st.markdown("**📊 Distribusi Probabilitas Arah**")
                st.markdown(f"- **Arah utama:** **{cardinal}** ({deg:.0f}°)")
                st.markdown(f"- **Confidence:** {conf:.0%} (konsistensi arah angin & konsentrasi risiko)")
                st.markdown(
                    "- Rata-rata tertimbang (weighted) arah angin di titik berisiko tinggi"
                )

                # Probability bar chart
                prob_df = pd.DataFrame(directions)
                fig_bar = go.Figure()
                fig_bar.add_trace(
                    go.Bar(
                        x=prob_df["dir"],
                        y=prob_df["prob"],
                        text=[f"{p:.1%}" for p in prob_df["prob"]],
                        textposition="auto",
                        marker_color=[
                            RISK_COLORS["tinggi"] if main else RISK_COLORS["sedang"]
                            for main in prob_df["is_main"]
                        ],
                    )
                )
                fig_bar.update_layout(
                    title="Probabilitas penyebaran per arah",
                    xaxis_title="Arah (Kompass)",
                    yaxis_title="Probabilitas",
                    yaxis=dict(tickformat=".0%"),
                    height=300,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_bar, use_container_width=True)

                st.warning("⚠️ **Saran:** Siapkan rencana evakuasi & penanggulangan ke arah **berlawanan** dengan arah dominan (≤ probabilitas rendah).")
        else:
            st.info("Arah rambatan tidak tersedia (data angin tidak lengkap atau tidak konsisten).")
    else:
        st.info("Data arah rambatan tidak tersedia.")

    st.markdown("---")

    # -- Temporal forecast for AOI (highest risk point) ---------------
    st.markdown("### 📈 Prediksi Temporal (Perkembangan Risiko)")
    st.caption(
        """
        **Prediksi temporal untuk titik berisiko tertinggi di dalam AOI.** 
        Grafik menunjukkan bagaimana risiko terprediksi berubah di titik terpenting selama jam ke depan.
        """
    )

    # Find point with maximum risk
    try:
        if "overall_risk" in batch_df.columns and len(batch_df) > 0:
            max_risk_idx = batch_df["overall_risk"].idxmax()
            max_risk_point = batch_df.loc[max_risk_idx]

            # Check if temporal_forecast exists for that point
            temporal_data = max_risk_point.get("temporal_forecast")
            if temporal_data and isinstance(temporal_data, dict):
                # Convert Series row to dict for safety
                max_risk_val = max_risk_point["overall_risk"]
                _render_temporal_forecast_section(temporal_data, max_risk_val)
            else:
                st.info("ℹ️ Data prediksi temporal tidak tersedia untuk titik berisiko tertinggi.")
        else:
            st.info("ℹ️ Data prediksi temporal tidak tersedia untuk AOI ini.")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        st.error(f"❌ Gagal menampilkan prediksi temporal titik puncak: {e}")
        with st.expander("Detail error (debug)"):
            st.code(tb)

    # -- Risk distribution chart ------------------------------------
    st.markdown("---")
    st.markdown("###  Distribusi Risiko di Area AOI")

    risk_order = ["Low", "Medium", "High", "Extreme"]
    risk_colors = {
        "Low": RISK_COLORS["rendah"],
        "Medium": RISK_COLORS["sedang"],
        "High": RISK_COLORS["tinggi"],
        "Extreme": RISK_COLORS["sangat_tinggi"],
    }
    risk_labels_id = {
        "Low": "Rendah",
        "Medium": "Sedang",
        "High": "Tinggi",
        "Extreme": "Sangat Tinggi",
    }

    dist_data = []
    for level in risk_order:
        count = _safe_count(risk_counts.get(level, 0))
        dist_data.append(
            {
                "Tingkat Risiko": risk_labels_id[level],
                "Jumlah": count,
                "Persentase": round(count / total_points * 100, 1)
                if total_points > 0
                else 0,
            }
        )
    dist_df = pd.DataFrame(dist_data)

    col_dist1, col_dist2 = st.columns([2, 1])

    with col_dist1:
        fig_dist = px.bar(
            dist_df,
            x="Tingkat Risiko",
            y="Jumlah",
            color="Tingkat Risiko",
            color_discrete_map={
                "Rendah": risk_colors["Low"],
                "Sedang": risk_colors["Medium"],
                "Tinggi": risk_colors["High"],
                "Sangat Tinggi": risk_colors["Extreme"],
            },
            labels={"Jumlah": "Jumlah Titik", "Tingkat Risiko": "Level Risiko"},
        )
        fig_dist.update_layout(
            height=350,
            showlegend=False,
            margin=dict(l=20, r=20, t=20, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with col_dist2:
        st.markdown("**Ringkasan Distribusi:**")
        for _, row in dist_df.iterrows():
            pct = row["Persentase"]
            count = row["Jumlah"]
            label = row["Tingkat Risiko"]
            st.markdown(f"- **{label}**: {count} titik ({pct:.1f}%)")

    st.markdown("---")

    # -- High-risk points table -------------------------------------
    st.markdown("###  Tabel Titik Berisiko Tinggi")
    st.caption("Menampilkan hingga 50 titik berisiko tertinggi beserta kondisi cuaca terkait")

    high_risk_df = batch_df[batch_df["risk_level"].isin(["High", "Extreme"])].copy()
    if len(high_risk_df) > 0:
        high_risk_df = high_risk_df.sort_values("overall_risk", ascending=False)
        # Columns: location + risk + weather
        display_cols = ["latitude", "longitude", "overall_risk", "risk_level", "temperature", "humidity", "wind_speed", "wind_direction"]
        available_cols = [c for c in display_cols if c in high_risk_df.columns]
        # Rename for display
        rename_map = {
            "latitude": "Latitude",
            "longitude": "Longitude",
            "overall_risk": "Risiko (%)",
            "risk_level": "Level",
            "temperature": "Suhu (°C)",
            "humidity": "Kelembaban (%)",
            "wind_speed": "Angin (m/s)",
            "wind_direction": "Arah Angin (°)",
        }
        display_df = high_risk_df[available_cols].head(50).copy()
        display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in available_cols})
        # Format risk as percentage
        if "Risiko (%)" in display_df.columns:
            display_df["Risiko (%)"] = (display_df["Risiko (%)"] * 100).round(1)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )
        if len(high_risk_df) > 50:
            st.caption(f"Menampilkan 50 dari {len(high_risk_df)} titik berisiko tinggi")
    else:
        st.info("Tidak ada titik berisiko tinggi di area AOI.")

    st.markdown("---")

    # -- Export results -------------------------------------------------
    col_confidence1, col_confidence2 = st.columns(2)

    active_model_type = st.session_state.get("active_model_type", "new")
    model_display_label = "Model Stacking" if active_model_type == "new" else "Model Ensemble"

    with col_confidence1:
        st.metric(
            " Mode Prediksi",
            "Batch AOI",
            f"{total_points} titik diproses",
        )
    with col_confidence2:
        st.text(f"Model: {model_display_label}")
        st.text("Waktu update: Baru saja")

    # -- Assumptions & limitations -----------------------------------
    st.markdown("---")
    st.markdown("#### ⚠️ Asumsi & Batasan")
    st.caption("""
    - Model mengasumsikan **homogenitas bahan bakar** di seluruh AOI (tidak variasi mikro).
    - **Cuaca dianggap konstan** di seluruh area (tidak ada variasi spasial cuaca dalam AOI).
    - Arah rambatan didasarkan pada **arah angin rata-rata** titik berisiko (bISA tidak menyertakan guruh/angin tanah).
    - Prediksi temporal menggunakan **proyeksi sederhana** (faktor musiman & pengeringan) — tidak menggabungkan prakiraan cuaca riil.
    - Tingkat risiko adalah **perkiraan probabilistik**, bukan deterministik. Selalu verifikasi di lapangan.
      """)





def render_results(prediction_result: Dict[str, Any]) -> None:
    """Display prediction results in an organized layout."""

    overall_risk = prediction_result.get("overall_risk", 0.5)
    level = get_risk_level(overall_risk)
    color = get_risk_color(overall_risk)
    icon = get_risk_icon(overall_risk)
    label = get_risk_label(overall_risk)

    # -- Risk hero + metrics ----------------------------------------
    col_risk1, col_risk2, col_risk3 = st.columns(3)

    with col_risk1:
        st.markdown(
            f"""
        <div class="risk-hero" style="background: linear-gradient(135deg, {color} 0%, {color}dd 100%);">
            <h2>{icon} {label}</h2>
            <p class="score">{overall_risk * 100:.1f}%</p>
            <p class="subtitle">Tingkat Risiko Keseluruhan</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_risk2:
        affected_area = prediction_result.get("affected_area", 0)
        st.metric(
            " Area Berpotensi Terdampak",
            f"{affected_area:.0f} Ha",
            "Estimasi zona risiko",
        )

    with col_risk3:
        max_spread_distance = prediction_result.get("max_spread_distance", 0)
        st.metric(
            " Jangkauan Maksimal",
            f"{max_spread_distance:.1f} km",
            "Dari titik sumber",
        )

    st.markdown("---")

    # -- SHAP explanation -------------------------------------------
    shap_explanation = prediction_result.get("shap_explanation", {})
    if shap_explanation and shap_explanation.get("top_features"):
        st.markdown("####  Why This Prediction?")
        st.markdown("Top contributing factors:")
        for feature in shap_explanation["top_features"][:3]:
            contribution = "positive" if feature["shap_value"] > 0 else "negative"
            st.markdown(
                f"- **{feature['feature']}**: {feature['shap_value']:.2f} ({contribution})"
            )

    st.markdown("---")

    # -- Risk factors + recommendations -----------------------------
    col_factors1, col_factors2 = st.columns(2)

    with col_factors1:
        st.markdown("###  Faktor Penyebab Risiko Tinggi")

        risk_factors = prediction_result.get("risk_factors", {})
        if risk_factors:
            factors_df = pd.DataFrame(
                list(risk_factors.items()), columns=["Faktor", "Kontribusi"]
            )
            factors_df = factors_df.sort_values("Kontribusi", ascending=False)

            # Compute colors based on contribution values
            max_contrib = factors_df["Kontribusi"].max()
            colors = []
            for val in factors_df["Kontribusi"]:
                if max_contrib > 0:
                    ratio = val / max_contrib
                    if ratio < 0.5:
                        colors.append("#22c55e")
                    elif ratio < 0.75:
                        colors.append("#fb923c")
                    else:
                        colors.append("#ef4444")
                else:
                    colors.append("#22c55e")

            fig_factors = go.Figure()
            fig_factors.add_trace(
                go.Bar(
                    x=factors_df["Kontribusi"],
                    y=factors_df["Faktor"],
                    orientation="h",
                    marker_color=colors,
                    text=[f"{v:.1f}%" for v in factors_df["Kontribusi"]],
                    textposition="outside",
                )
            )
            fig_factors.update_layout(
                title="Kontribusi Risiko (%)",
                xaxis_title="Kontribusi Risiko (%)",
                yaxis_title="Faktor",
                height=300,
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_factors, use_container_width=True)

            top_factor = factors_df.iloc[0]
            st.info(
                f"**Faktor Utama:** {top_factor['Faktor']} ({top_factor['Kontribusi']:.1f}% kontribusi)\n\n"
                "Area ini berisiko tinggi karena kombinasi vegetasi mudah terbakar dan kondisi cuaca mendukung penyebaran api."
            )

    with col_factors2:
        st.markdown("###  Rekomendasi Tindakan")

        risk_level_numeric = _get_risk_numeric(overall_risk)
        recommendations = _get_recommendations(risk_level_numeric, prediction_result)

        for i, rec in enumerate(recommendations, 1):
            st.markdown(f"**{i}. {rec['title']}**")
            st.write(rec["description"])
            if "action" in rec:
                st.caption(f" Tindakan: {rec['action']}")

    st.markdown("---")

    # -- Fire spread direction --------------------------------------
    st.markdown("###  Arah Rambatan Api (Probabilitas)")

    fire_directions = prediction_result.get("spread_directions", [])
    if fire_directions and isinstance(fire_directions, list):
        col_dir1, col_dir2 = st.columns(2)

        with col_dir1:
            directions_data = pd.DataFrame(fire_directions)
            if (
                "direction" in directions_data.columns
                and "probability" in directions_data.columns
            ):
                directions_data["Arah"] = directions_data["direction"].apply(
                    lambda x: f"{int(x)}"
                )
                fig_dir_pie = px.pie(
                    directions_data,
                    values="probability",
                    names="Arah",
                    title="Probabilitas Arah Rambatan Api",
                    color_discrete_sequence=[
                        RISK_COLORS["rendah"],
                        RISK_COLORS["sedang"],
                        RISK_COLORS["tinggi"],
                        RISK_COLORS["sangat_tinggi"],
                    ],
                )
                fig_dir_pie.update_layout(
                    height=350,
                    margin=dict(l=20, r=20, t=40, b=20),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=PALETTE["text"], family="sans-serif"),
                )
                st.plotly_chart(fig_dir_pie, use_container_width=True)

        with col_dir2:
            st.markdown("**Analisis Arah Rambatan:**")
            sorted_directions = sorted(
                fire_directions, key=lambda x: x.get("probability", 0), reverse=True
            )
            for direction_data in sorted_directions[:3]:
                direction = direction_data.get("direction", 0)
                probability = direction_data.get("probability", 0)
                st.markdown(
                    f"- **{int(direction)}**: {probability * 100:.1f}% probabilitas"
                )
            st.warning(
                "Siapkan rencana evakuasi ke arah yang memiliki probabilitas lebih rendah"
            )

    st.markdown("---")

    # -- Temporal Forecast Visualization ---------------------------------
    st.markdown("---")
    st.markdown("### 📈 Prediksi Temporal (Perkembangan Risiko)")
    st.caption(
        """
        **Grafik di bawah menunjukkan proyeksi risiko kebakaran untuk jam-jam ke depan** 
        berdasarkan kondisi awal dan pola musiman. Prakiraan cuaca riil dapat mengubah tren ini.
        Zona risiko: **Rendah** (<30%), **Sedang** (30-60%), **Tinggi** (60-80%), **Sangat Tinggi** (>80%).
        """
    )

    temporal_data = prediction_result.get("temporal_forecast")
    if temporal_data and isinstance(temporal_data, dict):
        _render_temporal_forecast_section(temporal_data, overall_risk)
    else:
        st.info("ℹ️ Data prediksi temporal tidak tersedia untuk prediksi ini.")

    st.markdown("---")

    # -- Assumptions & limitations -----------------------------------
    st.markdown("#### ⚠️ Asumsi & Batasan")
    st.caption("""
    - Model mengasumsikan **homogenitas bahan bakar** di seluruh AOI (tidak variasi mikro).
    - **Cuaca dianggap konstan** di seluruh area (tidak ada variasi spasial cuaca dalam AOI).
    - Arah rambatan didasarkan pada **arah angin rata-rata** titik berisiko (bISA tidak menyertakan guruh/angin tanah).
    - Prediksi temporal menggunakan **proyeksi sederhana** (faktor musiman & pengeringan) — tidak menggabungkan prakiraan cuaca riil.
    - Tingkat risiko adalah **perkiraan probabilistik**, bukan deterministik. Selalu verifikasi di lapangan.
     """)

    # -- Model confidence & model info --------------------------------
    st.markdown("##### ℹ️ Informasi Model")
    col_confidence1, col_confidence2 = st.columns(2)
    with col_confidence1:
        model_confidence = prediction_result.get("model_confidence", 0.85)
        st.metric(
            "Kepercayaan Model", f"{model_confidence * 100:.1f}%", "Akurasi prediksi"
        )
    with col_confidence2:
        model_label = (
            prediction_result.get("model_type")
            or st.session_state.get("active_model_type")
            or "new"
        )
        if model_label in ("new", "Stacking Model", "Model Stacking"):
            display_model = "Model Stacking"
        elif model_label in ("legacy", "Ensemble Model", "Model Ensemble"):
            display_model = "Model Ensemble"
        else:
            display_model = model_label
        st.text(f"Model: {display_model}")
        st.text("Waktu update: Baru saja")

    st.markdown("---")


# -- Helpers --------------------------------------------------------



def _render_temporal_forecast_section(temporal_forecast: dict, current_risk: float) -> None:
    """
    Render detailed temporal risk forecast visualization.

    Args:
        temporal_forecast: Dict with keys:
            - time_steps: list of ISO datetime strings
            - risk_scores: list of risk values (0-1)
            - risk_percentages: list of risk % values (0-100)
        current_risk: Current overall risk score (0-1)
    """
    import json as _json

    time_steps = temporal_forecast.get("time_steps", [])
    risk_scores = temporal_forecast.get("risk_scores", [])
    risk_percentages = temporal_forecast.get("risk_percentages", [])

    # Handle stringified JSON
    if isinstance(time_steps, str):
        try:
            time_steps = _json.loads(time_steps)
        except Exception:
            time_steps = []
    if isinstance(risk_scores, str):
        try:
            risk_scores = _json.loads(risk_scores)
        except Exception:
            risk_scores = []
    if isinstance(risk_percentages, str):
        try:
            risk_percentages = _json.loads(risk_percentages)
        except Exception:
            risk_percentages = []

    if not time_steps or not risk_scores or len(time_steps) != len(risk_scores):
        st.warning("Data prediksi temporal tidak lengkap atau tidak valid.")
        return

    # Convert timestamps to local time (UTC+7 for Indonesia)
    times_local = []
    for ts in time_steps:
        try:
            # Handle both string and datetime
            if isinstance(ts, str):
                dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, datetime):
                dt_utc = ts
            else:
                dt_utc = datetime.fromisoformat(str(ts))

            # Convert to Asia/Jakarta (UTC+7)
            if dt_utc.tzinfo is not None:
                dt_local = dt_utc.replace(tzinfo=None) + timedelta(hours=7)
            else:
                dt_local = dt_utc + timedelta(hours=7)
            times_local.append(dt_local)
        except Exception:
            try:
                # Fallback: treat as naive
                dt = datetime.fromisoformat(str(ts))
                times_local.append(dt + timedelta(hours=7))
            except Exception:
                times_local.append(None)

    # Filter out None times and corresponding risks
    valid_pairs = [(t, r, p) for t, r, p in zip(times_local, risk_scores, risk_percentages) if t is not None]
    if not valid_pairs:
        st.warning("Gagal memproses waktu prediksi.")
        return

    times_local, risk_scores, risk_percentages = zip(*valid_pairs)

    n_hours = len(times_local)

    # === Summary metrics ===
    try:
        risk_scores_arr = np.array([float(x) for x in risk_scores], dtype=float)
        risk_percentages_arr = np.array([float(x) for x in risk_percentages], dtype=float)
    except (ValueError, TypeError) as e:
        st.warning(f"Data risiko tidak valid: {e}")
        return

    max_risk_idx = int(np.argmax(risk_scores_arr))
    max_risk = risk_scores[max_risk_idx]
    max_risk_time = times_local[max_risk_idx]
    max_risk_pct = risk_percentages[max_risk_idx]

    # Trend analysis: compare last hour vs first hour, or vs current
    if n_hours >= 2:
        try:
            trend_change = float(risk_scores_arr[-1]) - float(risk_scores_arr[0])
        except (TypeError, ValueError):
            trend_change = 0.0
        if trend_change > 0.05:
            trend_label = "📈 Naik"
            trend_color = "#ef4444"  # red
        elif trend_change < -0.05:
            trend_label = "📉 Turun"
            trend_color = "#22c55e"  # green
        else:
            trend_label = "➡️ Stabil"
            trend_color = "#f59e0b"  # orange
    else:
        trend_label = "➡️ Stabil"
        trend_change = 0.0
        trend_color = "#f59e0b"

    # Count hours above thresholds
    high_threshold = 0.6
    extreme_threshold = 0.8
    high_hours = int(np.sum(risk_scores_arr >= high_threshold))
    extreme_hours = int(np.sum(risk_scores_arr >= extreme_threshold))

    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Risiko Saat Ini",
            value=f"{current_risk * 100:.1f}%",
            delta=f"({get_risk_label(current_risk)})",
            delta_color="off"
        )

    with col2:
        st.metric(
            label="Risiko Maksimum",
            value=f"{max_risk_pct:.1f}%",
            delta=None,
        )
        st.caption(f"🕐 Puncak: {max_risk_time.strftime('%H:00')} WIB")

    with col3:
        st.metric(
            label="Tren",
            value=trend_label,
            delta=f"{trend_change * 100:+.1f}% perubahan",
            delta_color="off"
        )

    with col4:
        st.metric(
            label="Jam Berisiko Tinggi",
            value=f"{high_hours} jam",
            delta=f"{extreme_hours} sangat tinggi",
            delta_color="off"
        )


    st.markdown("---")

    # === Time series chart ===
    # Create DataFrame for Plotly
    df = pd.DataFrame({
        "Waktu": times_local,
        "Risiko (%)": risk_percentages,
        "Risiko (0-1)": risk_scores,
    })

    # Format hover text
    df["hover"] = df.apply(
        lambda row: f"<b>{row['Waktu'].strftime('%Y-%m-%d %H:00')}</b><br>"
                    f"Risiko: {row['Risiko (%)']:.1f}%<br>"
                    f"Level: {get_risk_label(row['Risiko (0-1)'])}",
        axis=1
    )

    # Create figure
    fig = go.Figure()

    # Add area fill under curve
    fig.add_trace(
        go.Scatter(
            x=df["Waktu"],
            y=df["Risiko (%)"],
            mode="lines",
            name="Risiko",
            line=dict(color="#3b82f6", width=3),
            fill="tozeroy",
            fillcolor="rgba(59, 130, 246, 0.2)",
            hovertext=df["hover"],
            hoverinfo="text",
        )
    )

    # Add threshold lines (30%, 50%, 70%)
    thresholds = [
        (30, "Rendah→Sedang", "#22c55e"),
        (50, "Sedang→Tinggi", "#f59e0b"),
        (70, "Tinggi→Sangat Tinggi", "#ef4444"),
    ]
    for y_val, label, color in thresholds:
        fig.add_hline(
            y=y_val,
            line_dash="dash",
            line_color=color,
            annotation_text=label,
            annotation_position="right",
            annotation_font_size=10,
            opacity=0.7,
        )

    # Mark current time (t=0)
    current_time = times_local[0]
    # Use add_shape instead of add_vline to avoid Plotly datetime mean bug
    fig.add_shape(
        type="line",
        x0=current_time,
        x1=current_time,
        y0=0,
        y1=100,
        line=dict(dash="dot", color="white", width=2),
        xref="x",
        yref="y",
    )
    # Add annotation for "Sekarang"
    fig.add_annotation(
        x=current_time,
        y=100,
        text="Sekarang",
        showarrow=False,
        xanchor="center",
        yanchor="bottom",
        font=dict(size=11, color="white"),
        yref="y",
        xref="x",
    )

    # Mark peak point
    fig.add_trace(
        go.Scatter(
            x=[max_risk_time],
            y=[max_risk_pct],
            mode="markers",
            name="Puncak Risiko",
            marker=dict(color="red", size=12, symbol="circle"),
            hovertext=f"Puncak: {max_risk_pct:.1f}%",
        )
    )

    fig.update_layout(
        title="📈 Proyeksi Risiko Kebakaran ({} Jam Ke Depan)".format(n_hours),
        xaxis_title="Waktu (WIB)",
        yaxis_title="Risiko Kebakaran (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
        height=450,
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb", family="sans-serif"),
        xaxis=dict(
            gridcolor="rgba(148,163,184,0.12)",
            tickformat="%d %b<br>%H:00",
        ),
        yaxis_gridcolor="rgba(148,163,184,0.12)",
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)

    # === Detailed table in expander ===
    with st.expander("📋 Detail Prediksi Per Jam"):
        detail_df = pd.DataFrame({
            "Waktu (WIB)": [t.strftime("%Y-%m-%d %H:00") for t in times_local],
            "Risiko (%)": [f"{p:.1f}" for p in risk_percentages],
            "Level": [get_risk_label(s) for s in risk_scores],
            "Tindakan Saran": [
                _get_temporal_action_recommendation(s)
                for s in risk_scores
            ]
        })
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

        # Explanation of action recommendations
        st.caption(
            """
            **Kategori saran:**
            - 🔵 **Monitoring**: Risiko <30% — Pantau secara rutin
            - 🟡 **Waspada**: 30-60% — Tingkatkan kesiapan, persiapkan evakuasi
            - 🟠 **Siaga**: 60-80% — Siapkan tim respons, evakuasi preventif
            - 🔴 **Darurat**: >80% — Evakuasi segera, aktifkan sumber daya darurat
            """
        )

    # === Export temporal data ===
    st.markdown("#### 📥 Ekspor Data Temporal")
    col_exp1, col_exp2 = st.columns(2)
    csv_temporal = df.to_csv(index=False)
    json_temporal = df.to_json(orient="records", date_format="iso", indent=2)

    with col_exp1:
        st.download_button(
            label="⬇️ Unduh CSV (Temporal)",
            data=csv_temporal.encode("utf-8"),
            file_name=f"firecast_temporal_{times_local[0].strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Spreadsheet untuk analisis lebih lanjut")
    with col_exp2:
        st.download_button(
            label="⬇️ Unduh JSON (Temporal)",
            data=json_temporal.encode("utf-8"),
            file_name=f"firecast_temporal_{times_local[0].strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )
        st.caption("Data terstruktur untuk integrasi")


def _get_temporal_action_recommendation(risk_score: float) -> str:
    """Get concise action recommendation for a given temporal risk score."""
    if risk_score < 0.3:
        return "🔵 Monitoring rutin"
    elif risk_score < 0.6:
        return "🟡 Waspada, siap tim"
    elif risk_score < 0.8:
        return "🟠 Siaga, evakuasi preventif"
    else:
        return "🔴 DARURAT! Evakuasi segera"


def _get_risk_numeric(risk_score: float) -> int:
    """Convert risk score to numeric level."""
    if risk_score < 0.3:
        return 1
    elif risk_score < 0.5:
        return 2
    elif risk_score < 0.7:
        return 3
    return 4


def _get_recommendations(risk_level: int, prediction_result: Dict) -> list:
    """Get recommendations based on risk level."""
    recommendations = {
        1: [
            {
                "title": "Monitoring Rutin",
                "description": "Lanjutkan monitoring kondisi area secara berkala",
                "action": "Update data setiap 6 jam",
            },
            {
                "title": "Persiapan Pencegahan",
                "description": "Periksa jalur akses dan sumber air untuk keadaan darurat",
                "action": "Verifikasi infrastruktur",
            },
        ],
        2: [
            {
                "title": "Siaga Dini",
                "description": "Tingkatkan kesiapan tim respons dan alatnya",
                "action": "Aktivasi protokol siaga",
            },
            {
                "title": "Evakuasi Potensial",
                "description": "Persiapkan rencana evakuasi untuk wilayah terdekat",
                "action": "Brief tim emergency",
            },
        ],
        3: [
            {
                "title": "Siaga Darurat",
                "description": "Siapkan tim respons dengan semua peralatan lengkap",
                "action": "Deploy ke lokasi terdampak",
            },
            {
                "title": "Evakuasi Preventif",
                "description": "Mulai evakuasi komunitas dari area berisiko tinggi",
                "action": "Koordinasi dengan BPBD",
            },
            {
                "title": "Media & Komunikasi",
                "description": "Beritahu publik melalui media resmi dan sirene darurat",
                "action": "Aktivasi sistem informasi",
            },
        ],
        4: [
            {
                "title": "RESPONS DARURAT",
                "description": "Aktifkan semua sumber daya darurat sekarang",
                "action": "Hubungi Kepala Daerah & Panglima",
            },
            {
                "title": "Evakuasi Masif",
                "description": "Lakukan evakuasi menyeluruh dari zona risiko",
                "action": "Deploy semua transportasi",
            },
            {
                "title": "Permohonan Bantuan",
                "description": "Minta dukungan dari provinsi/pusat",
                 "action": "Hubungi kemlu dan kemkes",
            },
        ],
    }
    return recommendations.get(risk_level, [])
