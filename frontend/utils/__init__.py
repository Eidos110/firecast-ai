"""
Frontend utilities package — Streamlit-era imports removed during React SPA migration (2026-07-29).

The remaining modules here (theme, weather_api, gee_data, analytics, aoi_analysis,
i18n, log_handler, data_handler) are pure-Python reference implementations that
the React SPA (frontend_react/) intends to port to TypeScript endpoints on the
FastAPI backend (src/geo_api.py). They are kept as porting-reference for the
migration team until the equivalent TS implementations land in the SPA.

Do NOT import `prediction_engine` here anymore — that module was removed because
the React SPA calls `/predict` directly via fetch; the legacy Streamlit glue
that used to swap sys.modules['src.predict'] has been retired (AGENTS.md bug #8).

See docs/react-spa-migration/PLAN.md for the migration roadmap.
"""
from .weather_api import get_weather_data, is_demo_mode, get_weather_status
from .data_handler import load_model_features

__all__ = [
    'get_weather_data',
    'is_demo_mode',
    'get_weather_status',
    'load_model_features',
]
