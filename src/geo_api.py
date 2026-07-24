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
# Audit priority 2 — ORJSONResponse as default response class. orjson is a
# Rust-backed JSON encoder that is 2-3x faster than stdlib json for the
# numpy-array-heavy payloads we emit from /api/models and the future
# /predict REST endpoint. Falls back to FastAPI's default JSONResponse when
# orjson is unavailable (sandbox without the wheel) — correctness preserved.
try:
    from fastapi.responses import ORJSONResponse as _DefaultResponse
except Exception:  # pragma: no cover — orjson missing
    _DefaultResponse = None  # type: ignore[assignment]


def _response_class_factory():
    """Pick an appropriate default response class (sandbox-safe)."""
    if _DefaultResponse is not None:
        return _DefaultResponse
    from fastapi.responses import JSONResponse

    return JSONResponse


app = FastAPI(
    title="FireCast Geo API",
    default_response_class=_response_class_factory(),
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


# ---------------------------------------------------------------------------
# Admin cache endpoints (Audit priority 4)
#
# These let operators drop the in-memory caches WITHOUT restarting the server.
# Useful after the data CSV is regenerated with fresh rows, or after the
# model registry is mutated (the prediction cache may serve stale shap arrays
# otherwise). All endpoints are gated by the same ``X-API-Key`` used for
# /api/models/* and are rate-limited to 10/min to make scripted polling safe.
# ---------------------------------------------------------------------------
@app.post("/admin/cache/invalidate")
@limiter.limit("10/minute")
async def admin_cache_invalidate(request: Request, api_key: str = Depends(get_api_key)):
    """Drop every in-process cache so the next request recomputes fresh.

    Returns a dictionary describing what was cleared. Fails 500 only if the
    handler itself crashes (e.g. cache.load ImportError) — never silently 401.
    """
    cleared: dict[str, int] = {}

    # 1. CSV DataFrame cache (mtime-based _DataCache in this module)
    try:
        _data_cache.invalidate()
        cleared["csv_data_cache"] = 1
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("Failed to invalidate _data_cache: %s", e)
        cleared["csv_data_cache"] = 0

    # 2. Module-globals model loader cache (predict.py lazily binds
    #     load_cnn_model/load_lgbm_model/...). There is no module-global
    #     ``clear_model_cache`` symbol anymore (Fase 3 refactor); the only
    #     state worth dropping is the ``_init_models()`` success flag, which
    #     is reset by simply unbinding predict globals. Safe noop here.
    try:
        import src.predict as _predict_mod

        # Drop the runtime-bound model loaders so the next prediction
        # re-resolves them (catches stale file paths after registry changes).
        for _attr in (
            "load_cnn_model",
            "load_lgbm_model",
            "load_xgb_model",
            "predict_xgb",
            "load_causal_gru_model",
            "predict_causal_gru",
            "load_bigru_model",
            "predict_bigru",
            "evaluate_ensemble",
        ):
            if hasattr(_predict_mod, _attr):
                delattr(_predict_mod, _attr)
        cleared["model_cache"] = 1
    except Exception as e:  # pragma: no cover — graceful
        logger.debug("model cache invalidation skipped: %s", e)
        cleared["model_cache"] = 0

    # 3. Audit priority 2 — TTLCache used by predict_fire_risk(use_cache=True)
    try:
        from src.cache import cache_clear as _clear_pred_cache

        cleared["prediction_cache"] = int(_clear_pred_cache())
    except Exception as e:  # pragma: no cover
        logger.debug("prediction cache invalidation skipped: %s", e)
        cleared["prediction_cache"] = 0

    return {"status": "ok", "cleared": cleared}


@app.get("/admin/cache/stats")
@limiter.limit("30/minute")
async def admin_cache_stats(request: Request, api_key: str = Depends(get_api_key)):
    """Return a snapshot of every in-process cache for operational dashboards."""
    stats: dict[str, dict] = {}

    # Prediction TTLCache metadata (bounded TTL slot count, no payloads).
    try:
        from src.cache import cache_stats as _pred_stats

        stats["prediction_cache"] = _pred_stats()
    except Exception as e:  # pragma: no cover
        logger.debug("prediction cache stats skipped: %s", e)
        stats["prediction_cache"] = {"enabled": False}

    # CSV data cache snapshot — expose mtime + presence, not the DataFrame.
    try:
        stats["csv_data_cache"] = {
            "loaded": _data_cache._df is not None,
            "mtime_epoch": float(_data_cache._mtime),
        }
    except Exception as e:  # pragma: no cover
        stats["csv_data_cache"] = {"error": str(e)}

    return {"status": "ok", "stats": stats}


# ---------------------------------------------------------------------------
# Database & Persistence — Audit priority (Database & Persistence)
# ---------------------------------------------------------------------------
# Since we no longer deploy to Railway, there is no scheduled cron to compact
# the ``Prediction`` log table. These endpoints let operators purge old rows
# without a restart. Default window is 30 days, configurable via env var
# ``FIRECAST_PREDICTION_RETENTION_DAYS`` or directly through the query string.
# Both endpoints are gated by ``X-API-Key``.
# ---------------------------------------------------------------------------
@app.post("/admin/db/purge")
@limiter.limit("5/minute")
async def admin_db_purge(
    request: Request,
    api_key: str = Depends(get_api_key),
    days: int | None = None,
):
    """Run the Prediction retention policy and return deletion stats.

    Pass ``?days=14`` to override the env-configured window for this call
    only (e.g. rapid disk-clean during a prod incident).
    """
    try:
        from src.database import purge_old_predictions

        result = purge_old_predictions(days=days)
        return {"status": "ok", "result": result}
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("admin_db_purge failed: %s", e)
        return {"status": "error", "error": str(e)}


@app.get("/admin/db/stats")
@limiter.limit("30/minute")
async def admin_db_stats(request: Request, api_key: str = Depends(get_api_key)):
    """Return Prediction table row count + oldest/newest timestamps."""
    try:
        from src.database import prediction_stats

        result = prediction_stats()
        return {"status": "ok", "stats": result}
    except Exception as e:  # pragma: no cover
        return {"status": "error", "error": str(e)}
