"""Geospatial helpers for the FireCast API.

Submodules stay framework-free and importable without the SPA. The only
optional dependency is ``shapely`` (AOI point-in-polygon); it is imported
lazily and the grid falls back to the full bounding box when unavailable.
"""

from __future__ import annotations
