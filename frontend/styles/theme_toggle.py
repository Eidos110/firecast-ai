"""Dark/Light theme toggle for the Streamlit shell (Fase 4).

Streamlit does not natively support runtime theme switching, so we apply a
``data-theme`` attribute on ``<html>`` via a tiny JavaScript snippet. The
attribute drives the palette cascade defined by
:func:`frontend.utils.theme.get_css_variables` (``[data-theme="light"]``).

The chosen preference is persisted in ``localStorage`` (key ``firecast-theme``)
so it survives across sessions and is shared with the React component kit
(``frontend_react/src/theme/useTheme.ts`` reads the same key).
"""
from __future__ import annotations

import streamlit as st

_PREF_KEY = "firecast-theme"  # must match useTheme.ts STORAGE_KEY


def render_theme_toggle() -> None:
    """Inject the dark/light toggle button + the boot script that honours preference.

    Call once inside ``main()`` after :func:`inject_design_tokens`.
    The button is keyboard-accessible (real ``<button>`` with aria-label); the
    initial theme is read from ``localStorage`` then the OS preference.
    """
    st.session_state.setdefault("theme_kind", "dark")

    st.markdown(
        """
        <button
            id="firecast-theme-toggle"
            type="button"
            class="api-status"
            aria-label="Toggle color theme"
            title="Toggle dark / light theme"
            style="position: fixed; top: 8px; right: 12px; z-index: 9999;"
        >
            <span id="firecast-theme-glyph" aria-hidden="true"></span>
        </button>
        <script>
        (function () {
            var KEY = '""" + _PREF_KEY + """';
            var SR = 'dark';
            function apply(name) {
                document.documentElement.setAttribute('data-theme', name);
                var g = document.getElementById('firecast-theme-glyph');
                if (g) g.textContent = name === 'light' ? '\\u{1F313}' : '\\u{1F315}';
                try { localStorage.setItem(KEY, name); } catch (e) {}
            }
            function read() {
                try { var v = localStorage.getItem(KEY); if (v) return v; } catch (e) {}
                var prefers = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
                return prefers ? 'light' : 'dark';
            }
            apply(read());
            var btn = document.getElementById('firecast-theme-toggle');
            if (btn) {
                btn.addEventListener('click', function () {
                    var cur = (document.documentElement.getAttribute('data-theme') || 'dark');
                    apply(cur === 'light' ? 'dark' : 'light');
                });
            }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


__all__ = ["render_theme_toggle", "_PREF_KEY"]
