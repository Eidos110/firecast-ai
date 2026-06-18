"""
FireCast Design Token System
============================
Centralized color, spacing, and typography constants.
Used across CSS injection and Python component rendering.
"""

# ── Risk Level Colors ──────────────────────────────────────────────
RISK_COLORS = {
    "rendah": "#22c55e",
    "sedang": "#fb923c",
    "tinggi": "#ef4444",
    "sangat_tinggi": "#7f1d1d",
}

RISK_BG_COLORS = {
    "rendah": "rgba(34, 197, 94, 0.1)",
    "sedang": "rgba(251, 146, 60, 0.1)",
    "tinggi": "rgba(239, 68, 68, 0.1)",
    "sangat_tinggi": "rgba(127, 29, 29, 0.15)",
}

RISK_LABELS = {
    "id": {
        "rendah": "RENDAH",
        "sedang": "SEDANG",
        "tinggi": "TINGGI",
        "sangat_tinggi": "SANGAT TINGGI",
    },
    "en": {
        "rendah": "LOW",
        "sedang": "MEDIUM",
        "tinggi": "HIGH",
        "sangat_tinggi": "EXTREME",
    },
}

RISK_ICONS = {
    "rendah": "\U0001f7e2",  # 🟢
    "sedang": "\U0001f7e1",  # 🟡
    "tinggi": "\U0001f534",  # 🔴
    "sangat_tinggi": "\U0001f525",  # 🔥
}


def get_risk_level(score: float) -> str:
    """Return risk level key from a 0-1 score."""
    if score < 0.3:
        return "rendah"
    elif score < 0.5:
        return "sedang"
    elif score < 0.7:
        return "tinggi"
    return "sangat_tinggi"


def get_risk_color(score: float) -> str:
    """Return hex color for a risk score."""
    return RISK_COLORS[get_risk_level(score)]


def get_risk_bg_color(score: float) -> str:
    """Return background rgba color for a risk score."""
    return RISK_BG_COLORS[get_risk_level(score)]


def get_risk_label(score: float, locale: str = "id") -> str:
    """Return localized risk label."""
    level = get_risk_level(score)
    return RISK_LABELS.get(locale, RISK_LABELS["id"])[level]


def get_risk_icon(score: float) -> str:
    """Return emoji icon for a risk score."""
    return RISK_ICONS[get_risk_level(score)]


# ── General Palette ────────────────────────────────────────────────
PALETTE = {
    "primary": "#ef4444",
    "primary_light": "#fca5a5",
    "primary_dark": "#b91c1c",
    "accent": "#f59e0b",
    "success": "#22c55e",
    "info": "#3b82f6",
    "surface": "#1e293b",
    "surface_hover": "#334155",
    "background": "#0f172a",
    "text": "#f1f5f9",
    "text_muted": "#94a3b8",
    "border": "#334155",
}

# ── Typography Scale ────────────────────────────────────────────────
TYPOGRAPHY = {
    # Font families
    "font_primary": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif",
    "font_secondary": "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    
    # Font sizes (rem)
    "font_size_xs": "0.75rem",
    "font_size_sm": "0.875rem",
    "font_size_base": "1rem",
    "font_size_lg": "1.125rem",
    "font_size_xl": "1.25rem",
    "font_size_2xl": "1.5rem",
    "font_size_3xl": "1.875rem",
    "font_size_4xl": "2.25rem",
    
    # Line heights
    "line_height_tight": "1.2",
    "line_height_normal": "1.5",
    "line_height_relaxed": "1.75",
    
    # Font weights
    "font_weight_normal": "400",
    "font_weight_medium": "500",
    "font_weight_semibold": "600",
    "font_weight_bold": "700",
}

# ── Spacing Scale (px) ─────────────────────────────────────────────
SPACING = {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px",
    "2xl": "48px",
}

# ── Border Radius ──────────────────────────────────────────────────
RADIUS = {
    "sm": "4px",
    "md": "8px",
    "lg": "12px",
    "xl": "16px",
    "full": "9999px",
}

# ── Shadows ────────────────────────────────────────────────────────
SHADOW = {
    "sm": "0 1px 2px rgba(0,0,0,0.2)",
    "md": "0 4px 6px rgba(0,0,0,0.25)",
    "lg": "0 10px 15px rgba(0,0,0,0.3)",
    "card": "0 2px 8px rgba(0,0,0,0.2)",
    "card_hover": "0 8px 24px rgba(0,0,0,0.35)",
}


# ── CSS Custom Properties Injection ────────────────────────────────
def get_css_variables() -> str:
    """Return a CSS :root block with all design tokens as custom properties."""
    lines = [":root {"]
    for name, value in PALETTE.items():
        lines.append(f"  --color-{name.replace('_', '-')}: {value};")
    for name, value in RISK_COLORS.items():
        lines.append(f"  --risk-{name.replace('_', '-')}: {value};")
    for name, value in RISK_BG_COLORS.items():
        lines.append(f"  --risk-bg-{name.replace('_', '-')}: {value};")
    for name, value in SPACING.items():
        lines.append(f"  --spacing-{name}: {value};")
    for name, value in RADIUS.items():
        lines.append(f"  --radius-{name}: {value};")
    for name, value in SHADOW.items():
        lines.append(f"  --shadow-{name}: {value};")
    # Typography
    lines.append(f"  --font-primary: {TYPOGRAPHY['font_primary']};")
    lines.append(f"  --font-secondary: {TYPOGRAPHY['font_secondary']};")
    for name, value in TYPOGRAPHY.items():
        if name.startswith("font_size_"):
            lines.append(f"  --{name.replace('_', '-')}: {value};")
        elif name.startswith("line_height_"):
            lines.append(f"  --{name.replace('_', '-')}: {value};")
        elif name.startswith("font_weight_"):
            lines.append(f"  --{name.replace('_', '-')}: {value};")
    lines.append("}")
    return "\n".join(lines)


def get_global_font_import() -> str:
    """Return Google Fonts import link for Inter and JetBrains Mono."""
    return '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
