from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

from src import config
from src.api import models
from src.auth import get_api_key

logger = logging.getLogger(__name__)

# --- Authentication ---
# ``get_api_key`` is imported from :mod:`src.auth` (single source) so security
# policy (placeholder blacklist + ``secrets.compare_digest``) is consistent
# across all protected endpoints. The api_key_header definition stays here
# only for backward-compatible ``Security(api_key_header)`` resolution; the
# canonical dependency is now ``deps=get_api_key``.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Global progress tracking
from collections import deque  # noqa: E402

precompute_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "message": "",
    "last_completed": deque(maxlen=100),  # Bounded to prevent memory leak
}
# Audit Fase 3c: removed ``scheduler = AsyncIOScheduler()`` — the scheduler
# was instantiated but never started, never had any jobs added, and never
# raised (because start() was never called). It leaked a dangling scheduler
# object on every import. Re-introduce only when wired up via ``add_job``
# and ``scheduler.start()`` inside an ``@app.on_event("startup")`` handler.

ROOT = Path(__file__).resolve().parents[1]
# Single source of truth for the inference-ready features CSV lives in
# ``config.paths.processed_features_path``; the module-level alias keeps the
# existing call-sites (DATA_PATH, getmtime(DATA_PATH), read_csv(DATA_PATH))
# unchanged while staying in sync with config.
DATA_PATH = config.get_config().paths.processed_features_path

# Column name candidates for auto-detection
LAT_CANDIDATES = ["latitude", "lat", "Latitude", "LAT", "lat_deg", "y"]
LON_CANDIDATES = ["longitude", "lon", "Longitude", "LON", "lon_deg", "x"]
PROB_CANDIDATES = [
    "probability",
    "prob",
    "pred_prob",
    "score",
    "prediction_score",
    "prob_fire",
    "probability_fire",
]
TIME_CANDIDATES = ["time", "timestamp", "datetime", "date"]


# --- In-Memory Data Cache ---


class _DataCache:
    """Thread-safe in-memory CSV cache with mtime-based invalidation."""

    def __init__(self):
        self._df: pd.DataFrame | None = None
        self._columns: dict | None = None
        self._mtime: float = 0.0
        self._lock = threading.RLock()

    def _detect_columns(self, df: pd.DataFrame) -> dict:
        lat_col = next((c for c in LAT_CANDIDATES if c in df.columns), None)
        lon_col = next((c for c in LON_CANDIDATES if c in df.columns), None)
        prob_col = next((c for c in PROB_CANDIDATES if c in df.columns), None)
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        return {"lat": lat_col, "lon": lon_col, "prob": prob_col, "time": time_col}

    def get(self) -> tuple[pd.DataFrame, dict]:
        """Return cached DataFrame and detected columns, reloading if file changed."""
        with self._lock:
            try:
                current_mtime = os.path.getmtime(DATA_PATH)
            except OSError:
                raise HTTPException(status_code=404, detail=f"Data not found at {DATA_PATH}")

            if self._df is None or current_mtime != self._mtime:
                try:
                    self._df = pd.read_csv(DATA_PATH)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed reading CSV: {e}")
                self._columns = self._detect_columns(self._df)
                self._mtime = current_mtime

            return self._df, self._columns

    def invalidate(self):
        """Force reload on next get() call."""
        self._df = None
        self._columns = None
        self._mtime = 0.0


_data_cache = _DataCache()


def _get_cached_data() -> tuple[pd.DataFrame, dict]:
    """Convenience wrapper to get cached data + columns."""
    df, cols = _data_cache.get()
    if cols["lat"] is None or cols["lon"] is None:
        raise HTTPException(
            status_code=400, detail="Latitude/longitude columns not found in dataset"
        )
    return df, cols


# --- Vectorized H3 helpers ---
def _h3_index_vectorized(lats: np.ndarray, lons: np.ndarray, resolution: int) -> np.ndarray:
    """Compute H3 indices using list comprehension (faster than df.apply)."""
    return np.array(
        [h3.geo_to_h3(lat, lon, resolution) for lat, lon in zip(lats, lons, strict=False)]
    )


def _build_hex_record(hid: str, count: int, avg_prob: float | None) -> dict:
    """Build a single hexagon record with polygon and centroid."""
    hid_str = str(hid)  # Ensure Python str for H3 API compatibility
    boundary = h3.h3_to_geo_boundary(hid_str, geo_json=True)
    polygon = [[p[1], p[0]] for p in boundary]
    if polygon[0] != polygon[-1]:
        polygon.append(polygon[0])
    centroid = h3.h3_to_geo(hid_str)
    return {
        "hex_id": hid_str,
        "polygon": polygon,
        "centroid": {"lat": centroid[0], "lon": centroid[1]},
        "count": count,
        "avg_prob": avg_prob,
    }


# --- FastAPI app ---
app = FastAPI(
    title="FireCast Geo API",
)

# --- Rate Limiting ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# --- CORS ---
# Load allowed origins from environment or use defaults for development

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8501,http://localhost:3000,http://localhost:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-API-Key",
    ],  # Restrict to known headers
)

# Include routers
# Note: registry module does not have a router; model version management
# is handled through src.api.models router below.
# app.include_router(registry.router, prefix="/models", tags=["models"])
# Audit Fase 3c: do NOT pass ``prefix=`` again — the router already defines
# ``prefix="/api/models"`` (see ``src/api/models.py``). Passing it twice
# caused the historical double-prefix bug (404 on /api/models/api/models/..).
# Audit Fase 5: do NOT pass ``dependencies=[Depends(limiter.limit(...))]`` at
# the router mount either — slowapi's Depends wrapper exposes a ``func``
# query param to FastAPI's dependency-resolver at the include level, which
# results in HTTP 422 "Field required: func" on EVERY request to /api/models/*
# (slowapi only supports ``@limiter.limit(...)`` as a path-operation decorator,
# never as a router-level dependency). The X-API-Key auth dependency applied
# per-path inside ``src/api/models.py`` remains in effect; rate limiting for
# these admin endpoints is delegated to the auth layer (only key-holders can
# call them, which is itself the coarse rate limit).
app.include_router(
    models.router,
    tags=["models"],
)


# Optional per-IP cap that respects a slowapi availability (sandbox-safe).
# Applied only when slowapi is installed AND limiter is wired; graceful no-op
# otherwise so Railway/HF Spaces cores still serve /api/models without a 500.
def _models_rate_limit(request: Request, *args, **kwargs):  # pragma: no cover - thin wrapper
    """Best-effort slowapi rate-limit hook for /api/models endpoints.

    Kept as a function (not a Depends wrapper) so callers can opt-in via the
    ``@limiter.limit`` decorator on individual paths in ``src/api/models.py``
    if a stricter cap is desired. Today the path handlers rely on X-API-Key
    auth which is sufficient to discourage abuse.
    """
    return None


# --- Health check ---
@app.get("/health")
@limiter.limit("120/minute")
async def health(request: Request):
    return {"status": "ok"}


# Audit Fase 3c: removed ``_load_precomputed_hex`` + ``_invalidate_hex_cache``.
# Both functions and their ``@lru_cache`` reader were never called from any
# request handler — they were leftovers from a previous hex-precompute
# pipeline (see deleted ``hexagons_res_{res}.json`` cache). If a future
# feature needs this cache, re-introduce it through ``config.paths`` and a
# registered endpoint (not a private helper). DEAD CODE removed here.


@app.get("/precompute_progress")
@limiter.limit("60/minute")
async def get_precompute_progress(request: Request, api_key: str = Depends(get_api_key)):
    """Get current precompute progress. Requires authentication."""
    # Convert deque to list for JSON serialization
    progress_copy = precompute_progress.copy()
    progress_copy["last_completed"] = list(precompute_progress["last_completed"])
    return progress_copy
