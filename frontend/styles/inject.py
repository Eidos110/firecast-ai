"""Streamlit style injection helpers (Fase 4).

Extracts the giant inline ``<style>`` block out of ``frontend/app.py`` into
``frontend/styles/app.css`` and injects it exactly once per Streamlit session
(via ``st.session_state['_styles_injected']``). The CSS file uses a single
``{{CSS_VARS}}`` placeholder which is replaced with
:func:`frontend.utils.theme.get_css_variables` at runtime so the token system
stays the single source of truth.

Keeping the CSS outside ``app.py``:
- shrinks ``app.py`` (previously 1513 lines) by ~400 lines, making ``main()``
  easier to scan;
- lets designers edit the stylesheet without touching Python;
- re-renders are cheaper because the injected blob is reused (the session flag
  short-circuits subsequent re-runs).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import streamlit as st

from frontend.utils.theme import get_css_variables, get_global_font_import

logger = logging.getLogger(__name__)

_STYLES_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_CSS_PATH = os.path.join(_STYLES_DIR, "app.css")
_INJECT_FLAG = "_firecast_styles_injected"


@lru_cache(maxsize=1)
def _read_app_css() -> str:
    """Read and cache the raw app.css contents (with ``{{CSS_VARS}}`` placeholder)."""
    try:
        with open(_APP_CSS_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        logger.warning("app.css not found at %s — Streamlit will fall back to theme vars only.", _APP_CSS_PATH)
        return "{{CSS_VARS}}".replace("{{CSS_VARS}}", "")


def inject_design_tokens() -> None:
    """Inject Google Fonts + the full stylesheet once per Streamlit session.

    Idempotent: subsequent calls within the same session are no-ops. Safe to
    call at the top of ``main()`` on every re-run; the session flag guards
    against duplicate ``<style>`` tags.
    """
    if st.session_state.get(_INJECT_FLAG):
        return

    st.markdown(get_global_font_import(), unsafe_allow_html=True)
    css_vars = get_css_variables()
    body = _read_app_css().replace("{{CSS_VARS}}", css_vars)
    st.markdown(f"<style>\n{body}\n</style>", unsafe_allow_html=True)

    st.session_state[_INJECT_FLAG] = True


def reset_injection_flag() -> None:
    """Force re-injection on the next run (test helper)."""
    if _INJECT_FLAG in st.session_state:
        del st.session_state[_INJECT_FLAG]


__all__ = ["inject_design_tokens", "reset_injection_flag"]
