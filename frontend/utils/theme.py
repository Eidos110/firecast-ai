"""
FireCast Design Token System
============================
Centralized color, spacing, and typography constants.
Used across CSS injection and Python component rendering.

Single source of truth lives in ``frontend/themes/tokens.json`` (Fase 4).
This module mirrors the tokens back into Python-friendly constants and CSS
custom properties *so that existing call sites keep working unchanged*.

To regenerate after editing the JSON, call :func:`regenerate_from_tokens`
or simply re-import the module (the JSON is loaded lazily on first access
and cached). Hand-editing RISK_COLORS / PALETTE below is discouraged —
edit ``tokens.json`` instead.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_TOKENS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "themes",
    "tokens.json",
)

# Loader is implemented lazily below via :func:`_load_tokens`.


@lru_cache(maxsize=1)
def _load_tokens() -> Dict[str, Any]:
    """Load and cache the design-token JSON (single source of truth).

    Returns an empty dict on any error so that downstream code never crashes
    purely because the token file is missing or malformed — the hard-coded
    Python fallbacks below take over. A warning is logged.
    """
    try:
        with open(_TOKENS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning("Design tokens file not found at %s; using built-in fallbacks.", _TOKENS_PATH)
    except (ValueError, json.JSONDecodeError) as exc:  # malformed JSON
        logger.warning("Invalid design tokens JSON at %s: %s; using built-in fallbacks.", _TOKENS_PATH, exc)
    return {}


def _token_value(*path: str, default: Any = None) -> Any:
    """Resolve a nested ``{value: ...}`` node by dotted path, returning the inner ``value``.

    Token nodes follow the DTCG convention: ``{"value": <v>, "description"?: "..."}``.
    """
    node: Any = _load_tokens()
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
        if node is None:
            return default
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node if node is not None else default


def _token_section(section: str) -> Dict[str, Any]:
    """Return a top-level token section as a flat {key: value} dict (extracting inner ``value``)."""
    node = _load_tokens().get(section, {})
    if not isinstance(node, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in node.items():
        if k.startswith("$"):
            continue
        if isinstance(v, dict) and "value" in v:
            out[k] = v["value"]
        else:
            out[k] = v
    return out


# ── Risk Thresholds (single source of truth, scores 0-1) ──────────
# Keys map to lower-tier first: rendah < 0.3 <= sedang < 0.5 <= tinggi < 0.7 <= sangat_tinggi <= 1.0
RISK_THRESHOLDS = {
    "rendah": _token_value("risk_threshold", "rendah", default=0.3),
    "sedang": _token_value("risk_threshold", "sedang", default=0.5),
    "tinggi": _token_value("risk_threshold", "tinggi", default=0.7),
    "sangat_tinggi": _token_value("risk_threshold", "sangat_tinggi", default=1.0),
}

# ── Risk Level Colors ──────────────────────────────────────────────
RISK_COLORS = {
    "rendah": _token_value("color", "risk", "rendah", default="#22c55e"),
    "sedang": _token_value("color", "risk", "sedang", default="#fb923c"),
    "tinggi": _token_value("color", "risk", "tinggi", default="#ef4444"),
    "sangat_tinggi": _token_value("color", "risk", "sangat_tinggi", default="#7f1d1d"),
}

RISK_BG_COLORS = {
    "rendah": _token_value("color", "risk_bg", "rendah", default="rgba(34, 197, 94, 0.1)"),
    "sedang": _token_value("color", "risk_bg", "sedang", default="rgba(251, 146, 60, 0.1)"),
    "tinggi": _token_value("color", "risk_bg", "tinggi", default="rgba(239, 68, 68, 0.1)"),
    "sangat_tinggi": _token_value("color", "risk_bg", "sangat_tinggi", default="rgba(127, 29, 29, 0.15)"),
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
    """Return risk level key from a 0-1 score, using RISK_THRESHOLDS as single source."""
    if not isinstance(score, (int, float)):
        score = float(score or 0.0)
    rendah = RISK_THRESHOLDS.get("rendah", 0.3)
    sedang = RISK_THRESHOLDS.get("sedang", 0.5)
    tinggi = RISK_THRESHOLDS.get("tinggi", 0.7)
    # sangat_tinggi threshold is the upper bound (1.0); treat as catch-all above 'tinggi'.
    if score < rendah:
        return "rendah"
    elif score < sedang:
        return "sedang"
    elif score < tinggi:
        return "tinggi"
    return "sangat_tinggi"


def serialize_for_js() -> dict:
    """Return a JSON-safe dict mirroring risk thresholds + colors for JS clients.

    Thresholds are exposed as cumulative upper-bounds so JS can mirror
    get_risk_level via chained comparisons (< 0.3, < 0.5, < 0.7, else).
    """
    return {
        "thresholds": {
            "rendah": float(RISK_THRESHOLDS.get("rendah", 0.3)),
            "sedang": float(RISK_THRESHOLDS.get("sedang", 0.5)),
            "tinggi": float(RISK_THRESHOLDS.get("tinggi", 0.7)),
            "sangat_tinggi": float(RISK_THRESHOLDS.get("sangat_tinggi", 1.0)),
        },
        "colors": {
            level: str(RISK_COLORS.get(level, "#888888"))
            for level in RISK_THRESHOLDS
        },
        "bg_colors": {
            level: str(RISK_BG_COLORS.get(level, "rgba(128,128,128,0.1)"))
            for level in RISK_THRESHOLDS
        },
        "labels": {
            "id": {
                level: str(RISK_LABELS.get("id", {}).get(level, level))
                for level in RISK_THRESHOLDS
            },
            "en": {
                level: str(RISK_LABELS.get("en", {}).get(level, level.capitalize()))
                for level in RISK_THRESHOLDS
            },
        },
    }


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


# ── General Palette (dark theme is the default; light theme tokens below) ──
PALETTE = {
    "primary": _token_value("color", "base", "primary", default="#ef4444"),
    "primary_light": _token_value("color", "base", "primary_light", default="#fca5a5"),
    "primary_dark": _token_value("color", "base", "primary_dark", default="#b91c1c"),
    "accent": _token_value("color", "base", "accent", default="#f59e0b"),
    "success": _token_value("color", "base", "success", default="#22c55e"),
    "info": _token_value("color", "base", "info", default="#3b82f6"),
    "warning": _token_value("color", "base", "warning", default="#eab308"),
    "error": _token_value("color", "base", "error", default="#dc2626"),
    "surface": _token_value("color", "dark", "surface", default="#1e293b"),
    "surface_hover": _token_value("color", "dark", "surface_hover", default="#334155"),
    "background": _token_value("color", "dark", "background", default="#0f172a"),
    "text": _token_value("color", "dark", "text", default="#f1f5f9"),
    "text_secondary": _token_value("color", "dark", "text_secondary", default="#cbd5e1"),
    "text_muted": _token_value("color", "dark", "text_muted", default="#94a3b8"),
    "border": _token_value("color", "dark", "border", default="#334155"),
}

# Light-mode palette (Fase 4 dark/light toggle). Same key layout as PALETTE.
PALETTE_LIGHT = {
    "primary": _token_value("color", "base", "primary", default="#ef4444"),
    "primary_light": _token_value("color", "base", "primary_light", default="#fca5a5"),
    "primary_dark": _token_value("color", "base", "primary_dark", default="#b91c1c"),
    "accent": _token_value("color", "base", "accent", default="#f59e0b"),
    "success": _token_value("color", "base", "success", default="#22c55e"),
    "info": _token_value("color", "base", "info", default="#3b82f6"),
    "warning": _token_value("color", "base", "warning", default="#eab308"),
    "error": _token_value("color", "base", "error", default="#dc2626"),
    "surface": _token_value("color", "light", "surface", default="#ffffff"),
    "surface_hover": _token_value("color", "light", "surface_hover", default="#f1f5f9"),
    "background": _token_value("color", "light", "background", default="#f8fafc"),
    "text": _token_value("color", "light", "text", default="#0f172a"),
    "text_secondary": _token_value("color", "light", "text_secondary", default="#334155"),
    "text_muted": _token_value("color", "light", "text_muted", default="#64748b"),
    "border": _token_value("color", "light", "border", default="#e2e8f0"),
}

# ── Typography Scale ────────────────────────────────────────────────
TYPOGRAPHY = {
    # Font families
    "font_primary": _token_value("typography", "font_primary", default="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif"),
    "font_secondary": _token_value("typography", "font_secondary", default="'JetBrains Mono', 'Fira Code', 'Consolas', monospace"),

    # Font sizes (rem)
    "font_size_xs": _token_value("typography", "font_size", "xs", default="0.75rem"),
    "font_size_sm": _token_value("typography", "font_size", "sm", default="0.875rem"),
    "font_size_base": _token_value("typography", "font_size", "md", default="1rem"),
    "font_size_lg": _token_value("typography", "font_size", "lg", default="1.125rem"),
    "font_size_xl": _token_value("typography", "font_size", "xl", default="1.25rem"),
    "font_size_2xl": _token_value("typography", "font_size", "2xl", default="1.5rem"),
    "font_size_3xl": _token_value("typography", "font_size", "3xl", default="1.875rem"),
    "font_size_4xl": _token_value("typography", "font_size", "4xl", default="2.25rem"),

    # Line heights
    "line_height_tight": _token_value("typography", "line_height", "tight", default="1.2"),
    "line_height_normal": _token_value("typography", "line_height", "normal", default="1.5"),
    "line_height_relaxed": _token_value("typography", "line_height", "relaxed", default="1.75"),

    # Font weights
    "font_weight_normal": _token_value("typography", "font_weight", "normal", default="400"),
    "font_weight_medium": _token_value("typography", "font_weight", "medium", default="500"),
    "font_weight_semibold": _token_value("typography", "font_weight", "semibold", default="600"),
    "font_weight_bold": _token_value("typography", "font_weight", "bold", default="700"),
}

# ── Spacing Scale (px) ─────────────────────────────────────────────
SPACING = _token_section("spacing")
if not SPACING:
    SPACING = {
        "xs": "4px",
        "sm": "8px",
        "md": "16px",
        "lg": "24px",
        "xl": "32px",
        "2xl": "48px",
    }

# ── Border Radius ──────────────────────────────────────────────────
RADIUS = _token_section("radius")
if not RADIUS:
    RADIUS = {
        "sm": "4px",
        "md": "8px",
        "lg": "12px",
        "xl": "16px",
        "full": "9999px",
    }

# ── Shadows ────────────────────────────────────────────────────────
SHADOW = _token_section("shadow")
if not SHADOW:
    SHADOW = {
        "sm": "0 1px 2px rgba(0,0,0,0.2)",
        "md": "0 4px 6px rgba(0,0,0,0.25)",
        "lg": "0 10px 15px rgba(0,0,0,0.3)",
        "card": "0 2px 8px rgba(0,0,0,0.2)",
        "card_hover": "0 8px 24px rgba(0,0,0,0.35)",
    }

# ── Accessibility tokens (Fase 4) ──────────────────────────────────
A11Y = {
    "focus_ring": _token_value("a11y", "focus_ring", default="0 0 0 3px var(--color-accent)"),
    "touch_target_min": _token_value("a11y", "touch_target_min", default="44px"),
    "contrast_ratio_min": _token_value("a11y", "contrast_ratio_min", default=4.5),
}

# ── Motion tokens (Fase 4) ────────────────────────────────────────
MOTION = _token_section("motion")
if not MOTION:
    MOTION = {
        "duration_fast": "150ms",
        "duration_normal": "250ms",
        "duration_slow": "400ms",
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)",
    }

# ── z-index tokens (Fase 4) ───────────────────────────────────────
Z_INDEX = _token_section("z_index")
if not Z_INDEX:
    Z_INDEX = {
        "base": "0",
        "dropdown": "100",
        "sticky": "200",
        "toast": "9000",
        "modal": "1000",
        "command_palette": "1100",
    }


# ── CSS Custom Properties Injection ────────────────────────────────
def _palette_vars(palette: Dict[str, str]) -> list:
    """Build CSS var declarations for a palette dict (used for dark/light blocks)."""
    lines = []
    for name, value in palette.items():
        lines.append(f"  --color-{name.replace('_', '-')}: {value};")
    return lines


def _typography_vars() -> list:
    lines = []
    lines.append(f"  --font-primary: {TYPOGRAPHY['font_primary']};")
    lines.append(f"  --font-secondary: {TYPOGRAPHY['font_secondary']};")
    for name, value in TYPOGRAPHY.items():
        if name.startswith("font_size_"):
            lines.append(f"  --{name.replace('_', '-')}: {value};")
        elif name.startswith("line_height_"):
            lines.append(f"  --{name.replace('_', '-')}: {value};")
        elif name.startswith("font_weight_"):
            lines.append(f"  --{name.replace('_', '-')}: {value};")
    return lines


def _token_metric_vars(section_name: str, fallback: Dict[str, str], prefix: str) -> list:
    tokens = _token_section(section_name) or fallback
    return [f"  --{prefix}-{name}: {value};" for name, value in tokens.items()]


def get_css_variables() -> str:
    """Return a CSS block with all design tokens as custom properties.

    Emits:
      * ``:root`` — risk colors, spacing, radius, shadow, typography, motion,
        z-index, and a11y tokens (theme-agnostic).
      * ``:root, [data-theme="dark"]`` — dark-mode palette (default).
      * ``[data-theme="light"]`` — light-mode palette override.
    The ``data-theme`` attribute is applied to ``<html>`` by the Streamlit
    shell (see ``frontend/styles/theme_toggle.py``) and React shell
    (``frontend_react/src/theme/useTheme.ts``) so both frontends read the
    same tokens.
    """
    lines = [":root {"]
    # Theme-agnostic tokens
    for name, value in RISK_COLORS.items():
        lines.append(f"  --risk-{name.replace('_', '-')}: {value};")
    for name, value in RISK_BG_COLORS.items():
        lines.append(f"  --risk-bg-{name.replace('_', '-')}: {value};")
    for name, value in RISK_THRESHOLDS.items():
        lines.append(f"  --risk-threshold-{name.replace('_', '-')}: {value};")
    lines.extend(_token_metric_vars("spacing", SPACING, "spacing"))
    lines.extend(_token_metric_vars("radius", RADIUS, "radius"))
    lines.extend(_token_metric_vars("shadow", SHADOW, "shadow"))
    lines.extend(_token_metric_vars("motion", MOTION, "motion"))
    lines.extend(_token_metric_vars("z_index", Z_INDEX, "z"))
    for name, value in A11Y.items():
        lines.append(f"  --a11y-{name.replace('_', '-')}: {value};")
    lines.extend(_typography_vars())
    lines.append("}")

    # Dark-mode palette (default: applies to :root and explicit [data-theme=dark])
    lines.append(":root, [data-theme=\"dark\"] {")
    lines.extend(_palette_vars(PALETTE))
    lines.append("}")

    # Light-mode palette override
    lines.append("[data-theme=\"light\"] {")
    lines.extend(_palette_vars(PALETTE_LIGHT))
    lines.append("}")

    # Focus-visible + reduced-motion baseline (A11y Fase 4)
    lines.append(
        ":focus-visible {\n"
        f"  outline: none;\n"
        f"  box-shadow: {A11Y['focus_ring']};\n"
        f"}}"
    )
    lines.append(
        "@media (prefers-reduced-motion: reduce) {\n"
        "  *, *::before, *::after {\n"
        f"    animation-duration: {MOTION.get('duration_fast', '150ms')};\n"
        f"    transition-duration: {MOTION.get('duration_fast', '150ms')};\n"
        "  }\n"
        "}"
    )
    return "\n".join(lines)


def get_light_theme_css() -> str:
    """Return just the [data-theme=light] payload (handy for targeted injection)."""
    lines = ["[data-theme=\"light\"] {"]
    lines.extend(_palette_vars(PALETTE_LIGHT))
    lines.append("}")
    return "\n".join(lines)


def serialize_for_js_dark_light() -> Dict[str, Any]:
    """Return JS-safe palette for both themes (used by React useTheme hook)."""
    return {
        "dark": {k.replace("_", "-"): v for k, v in PALETTE.items()},
        "light": {k.replace("_", "-"): v for k, v in PALETTE_LIGHT.items()},
        "risk": {
            "colors": {lvl: RISK_COLORS[lvl] for lvl in RISK_THRESHOLDS},
            "bg_colors": {lvl: RISK_BG_COLORS[lvl] for lvl in RISK_THRESHOLDS},
            "thresholds": {lvl: float(RISK_THRESHOLDS[lvl]) for lvl in RISK_THRESHOLDS},
        },
        "a11y": {k.replace("_", "-"): v for k, v in A11Y.items()},
    }


def get_global_font_import() -> str:
    """Return Google Fonts import link for Inter and JetBrains Mono."""
    return '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
