"""Geospatial helpers for the FireCast Geo API (Tahap B).

Submodules here MUST stay Streamlit-free so they can be imported by the
REST backend without pulling the (deprecated) Streamlit component runtime.
Lazy import of optional deps (``geopandas``/``shapely``/``h3``) follows the
same policy as ``src/__init__.py`` — never eagerly require them.
"""

from __future__ import annotations
