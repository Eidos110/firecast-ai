"""
Render preview PNG untuk komponen UI FireCast (opsi 2).
Output: _preview_ui/preview_*.png

Komponen yang dirender:
  1. preview_shap_waterfall.png      -> SHAP waterfall (matplotlib)
  2. preview_temporal_band.png       -> Temporal forecast + probabilistic band (matplotlib)
  3. preview_risk_gauge.png          -> Risk gauge + status bar (matplotlib)
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Wedge
import matplotlib.patheffects as pe

OUT = os.path.dirname(os.path.abspath(__file__))

# Design tokens (mirror dari tokens.json)
COL_BG       = "#0f172a"
COL_SURFACE  = "#1e293b"
COL_BORDER   = "#334155"
COL_TEXT     = "#f1f5f9"
COL_TEXT_SEC = "#cbd5e1"
COL_TEXT_MUD = "#94a3b8"
COL_PRIMARY  = "#ef4444"
COL_ACCENT   = "#f59e0b"
COL_INFO     = "#3b82f6"
COL_SUCCESS  = "#22c55e"
RISK = {
    "rendah":        "#22c55e",
    "sedang":        "#fb923c",
    "tinggi":        "#ef4444",
    "sangat_tinggi": "#7f1d1d",
}
THRESH = {"rendah": 0.3, "sedang": 0.5, "tinggi": 0.7, "sangat_tinggi": 1.0}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": COL_TEXT,
    "axes.edgecolor": COL_BORDER,
    "axes.labelcolor": COL_TEXT_SEC,
    "xtick.color": COL_TEXT_SEC,
    "ytick.color": COL_TEXT_SEC,
    "figure.facecolor": COL_BG,
    "axes.facecolor": COL_SURFACE,
    "savefig.facecolor": COL_BG,
    "savefig.edgecolor": "none",
})


def get_risk_level(p: float) -> str:
    if p < THRESH["rendah"]:  return "rendah"
    if p < THRESH["sedang"]:  return "sedang"
    if p < THRESH["tinggi"]: return "tinggi"
    return "sangat_tinggi"


def _rounded_box(ax, x, y, w, h, fc, ec="none", alpha=1.0, lw=0):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.02",
                         fc=fc, ec=ec, alpha=alpha, lw=lw, mutation_aspect=1)
    ax.add_patch(box)


# =============================================================
# 1. SHAP WATERFALL
# =============================================================
def render_shap_waterfall():
    np.random.seed(42)
    base = 0.32  # base value (E[f(x)])
    feats = [
        ("temperature",       +0.118),
        ("humidity",          -0.082),
        ("wind_speed",        +0.064),
        ("ndvi",              +0.041),
        ("rainfall_24h",      -0.037),
        ("ffmc_index",        +0.029),
        ("dmc_index",         +0.018),
        ("temp_lag_1",        +0.012),
        ("rh_roll_3h",        -0.009),
        ("wind_dir_sin",      +0.005),
    ]
    names  = [f for f, _ in feats]
    values = [v for _, v in feats]
    cumulative = [base]
    for v in values:
        cumulative.append(cumulative[-1] + v)
    final = cumulative[-1]

    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=140)
    fig.subplots_adjust(left=0.22, right=0.97, top=0.88, bottom=0.10)

    # baseline
    ax.axvline(base, color=COL_TEXT_MUD, lw=1.2, ls="--", alpha=0.7)
    ax.text(base, -0.4, "base\n0.32", ha="center", va="top",
            color=COL_TEXT_MUD, fontsize=9)

    # bars
    for i, (name, v) in enumerate(feats):
        y = len(feats) - 1 - i
        x0 = cumulative[i]
        color = RISK["tinggi"] if v > 0 else RISK["rendah"]
        ax.barh(y, v, left=x0, color=color, alpha=0.92,
                edgecolor="none", height=0.62)
        # connector
        ax.plot([cumulative[i], cumulative[i + 1]], [y - 0.42, y - 0.42],
                color=COL_TEXT_MUD, lw=0.8, alpha=0.35)
        # label
        lbl_x = x0 + v + (0.006 if v >= 0 else -0.006)
        ax.text(lbl_x, y, f"{v:+.3f}", va="center",
                ha="left" if v >= 0 else "right",
                color=COL_TEXT, fontsize=9.5,
                fontweight="bold" if abs(v) > 0.05 else "normal")

    # final marker
    ax.scatter([final], [-0.85], s=140, color=get_risk_level_color(final),
               zorder=5, edgecolor=COL_TEXT, lw=1.5)
    ax.text(final, -1.25, f" f(x) = {final:.3f}\n {get_risk_label(final)}",
            ha="center", va="top", color=COL_TEXT, fontsize=10,
            fontweight="bold")

    ax.set_yticks(range(len(feats)))
    ax.set_yticklabels(list(reversed(names)))
    ax.set_xlabel("SHAP value (kontribusi ke output model)")
    ax.set_title("SHAP Waterfall  -  Top 10 Feature Contribution",
                 fontsize=14, fontweight="bold", pad=14, loc="left")
    ax.set_xlim(0.10, 0.65)
    ax.grid(axis="x", color=COL_BORDER, alpha=0.4, lw=0.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(COL_BORDER)
        spine.set_linewidth(0.8)

    # legend
    ax.plot([], [], "s", color=RISK["tinggi"], label="menaikkan risiko")
    ax.plot([], [], "s", color=RISK["rendah"], label="menurunkan risiko")
    leg = ax.legend(loc="lower right", frameon=True, framealpha=0.7,
                    facecolor=COL_SURFACE, edgecolor=COL_BORDER, fontsize=9)
    for t in leg.get_texts():
        t.set_color(COL_TEXT_SEC)

    out = os.path.join(OUT, "preview_shap_waterfall.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out}")


def get_risk_level_color(p):
    return RISK[get_risk_level(p)]

def get_risk_label(p):
    return {"rendah":"RENDAH","sedang":"SEDANG","tinggi":"TINGGI",
            "sangat_tinggi":"SANGAT TINGGI"}[get_risk_level(p)]


# =============================================================
# 2. TEMPORAL FORECAST + PROBABILISTIC BAND
# =============================================================
def render_temporal_band():
    from datetime import datetime, timedelta
    n = 24
    t0 = datetime(2026, 7, 26, 8, 0)
    times = [t0 + timedelta(hours=i) for i in range(n)]
    np.random.seed(7)
    base = 0.42
    # mengikuti kurva diurnal: puncak siang, turun malam
    diurnal = 0.18 * np.sin(np.linspace(0, 2*np.pi, n) + np.pi/2 - 1)
    trend   = np.linspace(0, 0.08, n)
    mean = np.clip(base + diurnal + trend + np.random.normal(0, 0.012, n), 0, 1)
    p10 = np.clip(mean - 0.06 - np.random.normal(0, 0.012, n), 0, 1)
    p90 = np.clip(mean + 0.06 + np.random.normal(0, 0.012, n), 0, 1)

    fig, ax = plt.subplots(figsize=(12, 6), dpi=140)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.86, bottom=0.16)

    # band p10-p90
    ax.fill_between(times, p10 * 100, p90 * 100,
                    color=COL_INFO, alpha=0.22, label="p10-p90 (90% CI)")
    # mean
    ax.plot(times, mean * 100, color=COL_INFO, lw=3, label="mean", zorder=4)

    # threshold lines pakai token (single source of truth)
    for thr, lbl, col in [
        (THRESH["rendah"], "Rendah-Sedang (30%)", RISK["rendah"]),
        (THRESH["sedang"], "Sedang-Tinggi (50%)", RISK["sedang"]),
        (THRESH["tinggi"], "Tinggi-Sangat Tinggi (70%)", RISK["tinggi"]),
    ]:
        ax.axhline(thr * 100, color=col, ls="--", lw=1.3, alpha=0.75)
        ax.text(times[-1], thr * 100 + 1.2, lbl, color=col, fontsize=9,
                ha="right", va="bottom", fontweight="bold")

    # peak marker
    peak_idx = int(np.argmax(mean))
    ax.scatter([times[peak_idx]], [mean[peak_idx] * 100], s=180,
               color=RISK["tinggi"], edgecolor=COL_TEXT, lw=1.8, zorder=6)
    ax.annotate(f"  Puncak: {mean[peak_idx]*100:.1f}%\n  {times[peak_idx].strftime('%H:00')} WIB",
                xy=(times[peak_idx], mean[peak_idx] * 100),
                xytext=(15, 12), textcoords="offset points",
                color=COL_TEXT, fontsize=10, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COL_TEXT, lw=1.2))

    # now marker
    ax.axvline(times[0], color=COL_TEXT, ls=":", lw=1.5, alpha=0.7)
    ax.text(times[0], 102, "SEKARANG", ha="center", va="bottom",
            color=COL_TEXT, fontsize=9, fontweight="bold",
            path_effects=[pe.withStroke(linewidth=2, foreground=COL_BG)])

    # color zones (background)
    ax.axhspan(0,  THRESH["rendah"] * 100, color=RISK["rendah"],    alpha=0.05, zorder=0)
    ax.axhspan(THRESH["rendah"] * 100, THRESH["sedang"]  * 100, color=RISK["sedang"],  alpha=0.05, zorder=0)
    ax.axhspan(THRESH["sedang"]  * 100, THRESH["tinggi"] * 100, color=RISK["tinggi"],  alpha=0.05, zorder=0)
    ax.axhspan(THRESH["tinggi"] * 100, 100,                          color=RISK["sangat_tinggi"], alpha=0.07, zorder=0)

    ax.set_ylim(0, 100)
    ax.set_ylabel("Risiko Kebakaran (%)")
    ax.set_xlabel("Waktu (WIB)")
    ax.set_title("Proyeksi Risiko Temporal (24 jam)  +  Probabilistic Band p10-p90",
                 fontsize=14, fontweight="bold", pad=12, loc="left")

    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:00"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")

    ax.grid(axis="y", color=COL_BORDER, alpha=0.35, lw=0.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(COL_BORDER)
        spine.set_linewidth(0.8)

    leg = ax.legend(loc="upper left", frameon=True, framealpha=0.7,
                    facecolor=COL_SURFACE, edgecolor=COL_BORDER, fontsize=9)
    for t in leg.get_texts():
        t.set_color(COL_TEXT_SEC)

    # caption bawah
    fig.text(0.08, 0.02,
             "Band p10-p90 merefleksikan ketidakpastian model.  "
             "Threshold konsisten dengan tokens.json (0.3 / 0.5 / 0.7),  "
             "BUKAN 0.3/0.6/0.8 seperti kode lama.",
             color=COL_TEXT_MUD, fontsize=9, style="italic")

    out = os.path.join(OUT, "preview_temporal_band.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out}")


# =============================================================
# 3. RISK GAUGE + STATUS BAR + MODEL CARD
# =============================================================
def render_risk_gauge():
    prob = 0.672
    ci_lo, ci_hi = 0.61, 0.73
    secondary = 0.648
    agree = 1 - abs(prob - secondary)
    level = get_risk_level(prob)
    color = RISK[level]
    label = get_risk_label(prob)

    fig = plt.figure(figsize=(13, 6), dpi=140)
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.3], wspace=0.18,
                          left=0.04, right=0.98, top=0.86, bottom=0.08)

    # ---- Status bar (simulasi header Streamlit) ----
    bar_ax = fig.add_axes([0.04, 0.91, 0.94, 0.05])
    bar_ax.set_xlim(0, 1); bar_ax.set_ylim(0, 1); bar_ax.axis("off")
    _rounded_box(bar_ax, 0, 0, 1, 1, COL_SURFACE)
    items = [
        ("● API OK",    COL_SUCCESS),
        ("Model: stacking v1.2 (AUC 0.89)", COL_TEXT),
        ("Demo: OFF",   COL_TEXT_SEC),
        ("RPM: 12/30",  COL_ACCENT),
        ("Latency: 142 ms", COL_TEXT_SEC),
        ("2026-07-26 08:14 WIB (UTC+7)", COL_TEXT_MUD),
    ]
    x_pos = 0.012
    for txt, col in items:
        bar_ax.text(x_pos, 0.5, txt, va="center", ha="left",
                    color=col, fontsize=10, fontfamily="monospace",
                    fontweight="bold" if col == COL_SUCCESS else "normal")
        x_pos += 0.16

    # ---- Left: Risk gauge (semi-circle) ----
    ax_g = fig.add_subplot(gs[0, 0])
    ax_g.set_aspect("equal"); ax_g.axis("off")
    ax_g.set_xlim(-1.3, 1.3); ax_g.set_ylim(-0.4, 1.25)

    # gauge background segments
    seg_bounds = [0, THRESH["rendah"], THRESH["sedang"], THRESH["tinggi"], 1.0]
    seg_cols  = [RISK["rendah"], RISK["sedang"], RISK["tinggi"], RISK["sangat_tinggi"]]
    for i in range(4):
        theta0 = 180 - seg_bounds[i+1] * 180
        theta1 = 180 - seg_bounds[i] * 180
        w = Wedge((0, 0), 1.0, theta0, theta1, width=0.22,
                  fc=seg_cols[i], alpha=0.28, ec="none")
        ax_g.add_patch(w)

    # active arc
    theta_act0 = 180 - prob * 180
    theta_act1 = 180
    ax_g.add_patch(Wedge((0, 0), 1.0, theta_act0, theta_act1,
                         width=0.22, fc=color, ec="none", alpha=0.95,
                         path_effects=[pe.withStroke(linewidth=1.5, foreground=COL_TEXT)]))

    # needle
    import math
    ang = math.radians(180 - prob * 180)
    ax_g.plot([0, 0.78 * math.cos(ang)], [0, 0.78 * math.sin(ang)],
              color=COL_TEXT, lw=3, solid_capstyle="round")
    ax_g.scatter([0], [0], s=140, color=COL_TEXT, zorder=6)
    ax_g.scatter([0], [0], s=50, color=COL_BG, zorder=7)

    # tick labels
    for v, lbl in [(0, "0"), (0.3, "30"), (0.5, "50"), (0.7, "70"), (1.0, "100")]:
        a = math.radians(180 - v * 180)
        ax_g.text(1.15 * math.cos(a), 1.15 * math.sin(a), f"{lbl}%",
                  ha="center", va="center", color=COL_TEXT_MUD, fontsize=9)

    # center value
    ax_g.text(0, 0.18, label, ha="center", va="center",
              color=color, fontsize=18, fontweight="bold")
    ax_g.text(0, -0.02, f"{prob*100:.1f}%", ha="center", va="center",
              color=COL_TEXT, fontsize=28, fontweight="bold")
    ax_g.text(0, -0.22, f"CI90 [{ci_lo*100:.0f}-{ci_hi*100:.0f}%]",
              ha="center", va="center", color=COL_TEXT_SEC, fontsize=10,
              fontfamily="monospace")
    ax_g.text(0, 1.18, "Tingkat Risiko Keseluruhan",
              ha="center", va="center", color=COL_TEXT_SEC, fontsize=11)
    ax_g.text(0, -0.34, f"● Sumber api", ha="center", va="top",
              color=color, fontsize=9)

    # ---- Right: Model card panel + secondary model agreement ----
    ax_c = fig.add_subplot(gs[0, 1])
    ax_c.axis("off")
    ax_c.set_xlim(0, 1); ax_c.set_ylim(0, 1)
    _rounded_box(ax_c, 0, 0, 1, 1, COL_SURFACE, ec=COL_BORDER, lw=1, alpha=0.6)

    rows = [
        ("[MODEL CARD]", "header"),
        ("Model type",      "Stacking (LGB + XGB  Causal-GRU meta)"),
        ("Version",         "v1.2  (registered 2026-06-15)"),
        ("Trained on",      "FireCast-train.csv  (47,832 rows)"),
        ("Test AUC",        "0.894"),
        ("Test F1",         "0.831"),
        ("Features",        "19 raw  +  rolling/lag engineered"),
        ("Sequence length", "7 jam  (Causal-GRU)"),
        ("Calibration",     "Temperature scaling T=1.18"),
        ("Scaler",          "StandardScaler  (add_new_model/scaler.pkl)"),
        ("",                ""),
        ("[ENSEMBLE AGREEMENT]", "header"),
        ("Primary prob",     f"{prob*100:.1f}%  (color: {color})"),
        ("Secondary prob",   f"{secondary*100:.1f}%  (base learner meta)"),
        ("Agreement",        f"{agree*100:.0f}%  ( > 80% = konsisten)"),
    ]
    y = 0.96
    for k, v in rows:
        if v == "header":
            ax_c.text(0.03, y, k, color=COL_ACCENT, fontsize=11,
                      fontweight="bold", va="top")
            ax_c.plot([0.03, 0.97], [y - 0.025, y - 0.025],
                      color=COL_BORDER, lw=0.8, alpha=0.6)
            y -= 0.055
        elif k == "":
            y -= 0.025
        else:
            ax_c.text(0.05, y, k, color=COL_TEXT_MUD, fontsize=9.5, va="top")
            val_col = COL_TEXT
            if k == "Agreement":
                val_col = COL_SUCCESS if agree > 0.8 else COL_ACCENT
            elif k == "Test AUC" or k == "Test F1":
                val_col = COL_SUCCESS
            ax_c.text(0.42, y, v, color=val_col, fontsize=9.5, va="top",
                      fontfamily="monospace")
            y -= 0.045

    fig.suptitle("Risk Gauge  +  Model Provenance Card",
                 fontsize=15, fontweight="bold", y=0.98, x=0.04, ha="left")

    out = os.path.join(OUT, "preview_risk_gauge.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out}")


if __name__ == "__main__":
    render_shap_waterfall()
    render_temporal_band()
    render_risk_gauge()
    print("\n--- semua preview selesai ---")
