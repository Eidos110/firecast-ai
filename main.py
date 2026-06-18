"""
Railpack / generic Python runner bridge.
Railpack (and similar build systems) auto-detect `main:app` as the
FastAPI entry-point.  We re-export the real FastAPI app from
src.geo_api:app so the auto-detected start command works without extra
configuration.
"""
import sys
import os

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.geo_api import app  # noqa: F401 – re-export
