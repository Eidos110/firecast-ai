from __future__ import annotations

import logging
import os
import threading
from collections import deque
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from src import config
from src.api import models
from src.auth import get_api_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# H3 v3 vs v4 compatibility shim (Audit rekomendasi "Geospatial").
# h3 4.x renamed the public API:
#   geo_to_h3          -> latlng_to_cell
#   h3_to_geo          -> cell_to_latlng
#   h3_to_geo_boundary -> cell_to_boundary  (returns list[tuple] instead of
#                                  list[list] when ``geo_json=False``)
#   h3_to_parent       -> cell_to_parent
# ``requirements.txt`` pins ``h3>=3.7.6`` but the live FIREvCPU env has 4.5.0
# installed. Both branches are therefore exercised and must keep working.
# ---------------------------------------------------------------------------
def _h3_latlng_to_cell(lat: float, lon: float, res: int) -> str:
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lon, res)
    return h3.geo_to_h3(lat, lon, res)  # type: ignore[attr-defined]


def _h3_cell_to_latlng(cell: str) -> tuple[float, float]:
    if hasattr(h3, "cell_to_latlng"):
        return h3.cell_to_latlng(cell)
    return h3.h3_to_geo(cell)  # type: ignore[attr-defined]


def _h3_cell_to_boundary(cell: str) -> list[tuple[float, float]]:
    """Return polygon ring as ``[(lat, lon), ...]`` regardless of h3 version."""
    if hasattr(h3, "cell_to_boundary"):
        # v4: returns list[tuple[float, float]] of (lat, lon) already.
        return list(h3.cell_to_boundary(cell))
    # v3: geo_json=True swaps to (lon, lat); we keep (lat, lon) order.
    return list(h3.h3_to_geo_boundary(cell, geo_json=False))  # type: ignore[attr-defined]


# --- Authentication ---
# ``get_api_key`` is imported from :mod:`src.auth` (single source) so security
# policy (placeholder blacklist + ``secrets.compare_digest``) is consistent
# across all protected endpoints. The api_key_header definition stays here
# only for backward-compatible ``Security(api_key_header)`` resolution; the
# canonical dependency is now ``deps=get_api_key``.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Global progress tracking

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
# Audit rekomendasi "Geospatial _h3_index_vectorized ke np.vectorize":
# replace the Python list-comprehension with ``np.vectorize`` (small but
# measurable speed-up on >100-point AOI batches) AND layer a small bounded
# cache keyed by (lat, lon, resolution) on top, so repeated Streamlit reruns
# against the same lat/lon skip the H3 call entirely.
@lru_cache(maxsize=4096)
def _h3_index_cached(lat: float, lon: float, resolution: int) -> str:
    """Return the H3 cell string for ``(lat, lon)`` at ``resolution``.

    Cached per (lat, lon, resolution) — bounded to 4096 entries so the cache
    does not grow unbounded across long-lived workers. ``str`` keys are
    hashable and stable across Python processes.
    """
    return _h3_latlng_to_cell(lat, lon, resolution)


# ``np.vectorize`` is not a true ufunc — it is a convenience wrapper that
# still loops in Python — but it returns a real ``np.ndarray`` (object dtype
# when the underlying result is str), which is what callers expect. The
# cache above is what actually buys throughput; ``np.vectorize`` is mainly
# for API consistency and to document intent.
_h3_index_ufunc = np.vectorize(_h3_index_cached, otypes=[object])


def _h3_index_vectorized(
    lats: np.ndarray, lons: np.ndarray, resolution: int
) -> np.ndarray:
    """Compute H3 indices vectorised + cached per (lat, lon, res).

    Args:
        lats: 1-D or 2-D array of latitudes.
        lons: 1-D or 2-D array of longitudes (same shape as ``lats``).
        resolution: H3 resolution (0–15).

    Returns:
        ``np.ndarray`` of ``str`` H3 indices, same shape as ``lats``.
    """
    if lats.shape != lons.shape:
        raise ValueError(
            f"lats {lats.shape} and lons {lons.shape} must have equal shape"
        )

    # Flatten 2-D AOI grids — both the lru_cache path and the ndarray reshape
    # below work best on contiguous 1-D input.
    original_shape = lats.shape
    flat_lats = lats.ravel()
    flat_lons = lons.ravel()

    # De-duplicate (lat, lon) pairs before calling the H3 encoder
    # (ROADMAP §2-F): for AOI batches with repeated coordinates (common
    # when Streamlit re-renders or when hexagon tessellation overlaps),
    # ``np.unique`` collapses the unique (lat, lon) pairs into a small
    # working set. H3 is then called once per unique pair — an O(unique)
    # operation — instead of once per sample. The result is ``scatter``-ed
    # back to the original ordering via the ``inv`` inverse map, so the
    # output is bitwise identical to the naive per-point version.
    #
    # ``np.unique`` with ``axis=0`` + ``return_inverse=True`` runs in
    # C on the contiguous view, making it cheap even for 10k-point AOIs.
    latlon = np.column_stack([flat_lats, flat_lons])
    uniq, inv = np.unique(latlon, axis=0, return_inverse=True)

    # Call the (lru-cached) H3 encoder on the dedup'd coordinate set only.
    uniq_cells = _h3_index_ufunc(uniq[:, 0], uniq[:, 1], resolution)

    # Scatter back to the original ordering. ``uniq_cells[inv]`` is an
    # ``ndarray`` of the same shape as ``flat_lats``.
    flat_cells = uniq_cells[inv]
    return flat_cells.reshape(original_shape)


def _build_hex_record(hid: str, count: int, avg_prob: float | None) -> dict:
    """Build a single hexagon record with polygon and centroid."""
    hid_str = str(hid)  # Ensure Python str for H3 API compatibility
    # Use the v3/v4 compat shim — h3.h3_to_geo_boundary was renamed to
    # cell_to_boundary in v4. We always return (lat, lon) tuples here and
    # swap to (lon, lat) for GeoJSON polygon (geo_api always emits GeoJSON).
    boundary_latlon = _h3_cell_to_boundary(hid_str)
    polygon = [[p[1], p[0]] for p in boundary_latlon]
    if polygon[0] != polygon[-1]:
        polygon.append(polygon[0])
    centroid = _h3_cell_to_latlng(hid_str)
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
# numpy-array-heavy payloads we emit from /predict, /predict/aoi, and
# /api/models (ROADMAP §2-H). Falls back to FastAPI's default JSONResponse
# when orjson is unavailable (sandbox without the wheel) — correctness
# preserved. orjson natively serialises numpy scalars/arrays via
# ``orjson.OPT_SERIALIZE_NUMPY`` under the hood of ORJSONResponse.
try:
    from fastapi.responses import ORJSONResponse as _DefaultResponse
except Exception:  # pragma: no cover — orjson missing
    _DefaultResponse = None  # type: ignore[assignment]


def _response_class_factory():
    """Pick an appropriate default response class (sandbox-safe).

    Prefers ``ORJSONResponse`` (2–3x faster JSON encode for the numpy-heavy
    /predict and /predict/aoi payloads; see ROADMAP §2-H). Falls back to
    FastAPI's stdlib ``JSONResponse`` when the ``orjson`` wheel is missing
    (e.g. a minimal sandbox) — behaviour stays correct either way.
    """
    if _DefaultResponse is not None:
        return _DefaultResponse
    from fastapi.responses import JSONResponse

    return JSONResponse


def _init_observability_sync() -> None:
    """Startup observability hook — extracted from the deprecated ``@app.on_event("startup")`` block.

    Idempotent, sandbox-safe: env vars only drive initialisation; missing
    sentry_sdk / opentelemetry libs fall back to no-op after logging. Never
    raises — an observability crash must not blackhole the whole app boot.
    """
    try:
        from src.observability import init_observability

        result = init_observability(
            service_name="firecast-api",
            environment=os.environ.get("APP_ENV", "development"),
        )
        # Log init outcome but never block startup on the result.
        if any(result.values()):
            logger.info("Observability initialised: %s", result)
        else:
            logger.debug("Observability no-op (no SENTRY_DSN/OTEL endpoint configured)")
    except Exception as e:  # pragma: no cover — never raise on observability
        logger.warning("Observability init skipped: %s", e)


@asynccontextmanager
async def _lifespan(app_instance: FastAPI):  # noqa: D401 - signature mandated by FastAPI
    """FastAPI lifespan (replaces deprecated ``@app.on_event("startup")``).

    Runs startup init before yielding; teardown currently no-op because the
    app is single-process / single-worker (no graceful-shutdown resource to
    release beyond what uvicorn handles). Kept as an explicit context
    manager so future shutdown hooks (cache flush, model unload) drop in
    without another compatibility migration.
    """
    _init_observability_sync()
    yield


app = FastAPI(
    title="FireCast Geo API",
    default_response_class=_response_class_factory(),
    lifespan=_lifespan,
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


# ---------------------------------------------------------------------------
# Startup — observability init moved to the ``_lifespan`` asynccontextmanager
# above (FastAPI 0.110+ deprecates ``@app.on_event("startup")``; a future
# release will remove the hook entirely).
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Task 6.6 (UI Revamp Fase 6) — Realize the ``/predict`` REST endpoint.
#
# PLAN §6.6 Opsi A: the copy-as-cURL button in ``right_diagnostic`` issues::
#
#     curl -X POST http://localhost:8000/predict \
#       -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
#       -d '{"latitude": -1.17, "longitude": 100.40, "temperature": 28, ...}'
#
# Before this task that 404'd. Now it mirrors the in-process
# ``src.predict.predict_fire_risk`` API surface so engineers can replay any
# Streamlit prediction outside the browser — exactly the engineer-UX contract
# PLAN §4 (Task 4.3) promises.
#
# Design notes:
#   * Auth via ``Depends(get_api_key)`` — same gate as ``/api/models/*``.
#     Anonymous requests get 401; never 403 (keeps cURL replay shallow).
#   * Rate-limit 30/minute per IP (PLAN §3 "Panduan API" cap for /predict;
#     OWM token bucket is independent and not bypassed here — caller still
#     needs valid OPENWEATHER_API_KEY for live weather if used).
#   * Pydantic models below keep optional fields Optional with default
#     ``None`` so a partial payload raises a *clear* 422 instead of silent
#     0.5 fallback (AGENTS.md §3 — never return 0.5 on model error).
#   * Lazily import ``predict_fire_risk`` so a crashed torch/h3 import does
#     not blackhole the whole app: the endpoint returns 500 with the
#     underlying ``PredictionError`` message, not a startup import error.
# ---------------------------------------------------------------------------
class PredictRequest(BaseModel):
    """Inbound features for ``/predict``.

    Mirrors the dict expected by :func:`src.predict.predict_fire_risk`.
    Required keys match ``predict.py:938-944`` (``required_keys``). Optional
    keys are those the Streamlit engine fills from GEE/OpenWeatherMap when
    available; their absence is graceful — predict_fire_risk tolerates it.
    """

    temperature: float = Field(..., description="Air temperature (°C)")
    humidity: float = Field(..., description="Relative humidity (%)")
    wind_speed: float = Field(..., description="Wind speed (m/s)")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (WGS84)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude (WGS84)")
    wind_direction: float | None = Field(default=None, description="Wind direction (deg from N)")
    rainfall: float | None = Field(default=None, description="Rainfall (mm)")
    ndvi: float | None = Field(default=None, description="Normalised Difference Vegetation Index (−1..1)")
    vegetation_type: str | None = Field(default=None, description="Vegetation class")
    fuel_moisture: float | None = Field(default=None, description="Fuel moisture content (%)")
    model_version: str | None = Field(
        default=None,
        description="Optional model version id. Defaults to registry active version.",
    )
    model_type: str = Field(
        default="new",
        description="'new' (stacking) or 'legacy' (CNN+LGBM). Default 'new'.",
    )
    reference_date: str | None = Field(
        default=None,
        description=(
            "Optional ISO date (``YYYY-MM-DD``) used as the temporal anchor "
            "for seasonal feature engineering. ROADMAP §3-W1 added this so "
            "the SPA Header date-scrubber can replay a past/future day. "
            "``None`` (default) ⇒ anchor to the server's current date "
            "(backwards compatible with all pre-W1 clients)."
        ),
    )


@app.post("/predict")
@limiter.limit("30/minute")
async def predict_endpoint(
    request: Request,
    payload: PredictRequest,
    api_key: str = Depends(get_api_key),
) -> dict:
    """Run a single fire-risk prediction and return the full result dict.

    Auth: ``X-API-Key`` header (same gate as ``/api/models/*``).
    Rate-limit: 30 requests/minute per IP (PLAN §3 + AGENTS.md §3 cap).

    Returns: the unconstrained JSON produced by ``predict_fire_risk`` —
    keys include ``risk_score, risk_level, confidence, cnn_probability,
    lgbm_probability, factors, shap_explanation, confidence_interval,
    model_agreement, timestamp, status``. ``run_id`` and ``latency_ms`` are
    added here for the engineer console raw-API expander.
    """
    # ---- lazily import predict module so a torch load failure breaks just
    # this request, not the entire app startup. AGENTS.md §3 "Lazy import":
    # apply the same `_get_X()`-style guard to a request-scoped path.
    try:
        from src.predict import PredictionError, predict_fire_risk
    except Exception as exc:  # pragma: no cover — depends on env
        logger.error("predict module import failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Prediction backend unavailable: {exc}",
        ) from exc

    # ---- convert Pydantic model to dict, dropping None values so we do not
    # override upstream defaults in predict_fire_risk with explicit None.
    import time as _time

    features = {k: v for k, v in payload.model_dump().items() if v is not None}
    # model_version / model_type / reference_date are predict_fire_risk
    # kwargs, not features.
    model_version = features.pop("model_version", None)
    model_type = features.pop("model_type", "new")
    reference_date_iso = features.pop("reference_date", None)

    # Parse ``reference_date`` (ROADMAP §3-W1). Reject malformed input as a
    # 422-style validation error rather than letting downstream ValueError
    # bubble through as a 500. Time-of-day is forced to noon UTC so the doy
    # is stable across client/server timezone skew.
    reference_date = None
    if reference_date_iso:
        try:
            from datetime import datetime as _dt

            reference_date = _dt.fromisoformat(f"{reference_date_iso}T12:00:00")
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"reference_date must be ISO YYYY-MM-DD, got {reference_date_iso!r}: {exc}",
            ) from exc

    started_ms = _time.perf_counter()
    try:
        result = predict_fire_risk(
            features=features,
            model_version=model_version,
            model_type=model_type,
            use_cache=True,  # REST replay is idempotent → cache-friendly
            reference_date=reference_date,
        )
    except PredictionError as exc:
        # Never return 0.5 silently (AGENTS.md §3). Surface the message so
        # the engineer can debug.
        logger.warning("predict endpoint PredictionError: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("predict endpoint unexpected error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    # ---- augment with engineer-console provenance (right_diagnostic reads
    # these keys via `prediction_result.get("run_id")` etc.). run_id is
    # derived from the active model version so cURL replay and the UI show
    # identical provenance for the same model.
    #
    # Bug fix 2026-07-31: ``get_active_model_version`` is a required-arg
    # helper (``registry.py:20``); calling it without ``model_name`` raised
    # TypeError inside the swallowed try/except, so ``run_id`` was NEVER
    # added to the response. The frontend then crashed in
    # ``ModelSelectPanel.runInference`` on ``(result.run_id as string).split``
    # (undefined). Map the request's ``model_type`` to a logical registry
    # name and always emit a non-empty ``run_id`` (deterministic fallback
    # when no version is registered yet).
    latency_ms = round((_time.perf_counter() - started_ms) * 1000.0, 3)
    result.setdefault("latency_ms", latency_ms)
    registry_name = "stacking" if model_type == "new" else "legacy"
    run_id: str | None = None
    try:
        from src.models.registry import get_active_model_version

        active = get_active_model_version(registry_name)
        if active is not None:
            version = getattr(active, "version", None) or getattr(active, "version_string", None)
            if version:
                run_id = f"{registry_name}-{version}"
    except Exception:  # pragma: no cover — registry is optional
        pass
    if not run_id:
        # Deterministic synthetic id so the UI (header pill, run_id pill,
        # setRunId, setActiveModel) never receives ``undefined``.
        import time as _ts

        run_id = f"{registry_name}-adhoc-{int(_ts.time() * 1000)}"
    result.setdefault("run_id", run_id)

    return result


# ---------------------------------------------------------------------------
# TAHAP B — Geo / Analytics / AOI endpoints (React SPA migration PLAN §3)
#
# Four read-mostly routes that the new React SPA needs and that previously
# only existed as in-process Streamlit helper calls.
#
# Auth & rate-limit policy (PLAN §1 + AGENTS.md §3):
#   * ``/geo/locations`` and ``/analytics/trend`` are public-read (no X-API-Key)
#     because the SPA's left-sidebar city combobox and chart need to work
#     for anonymous users on a hosted demo. Rate-limited so a bot cannot
#     use them as a free city-dump endpoint.
#   * ``/geo/geocode`` is public-read too — Tier-2 Nominatim fallback is
#     itself rate-limited upstream (1 req/sec per app) so the FastAPI cap
#     just protects our worker, not the upstream.
#   * ``/predict/aoi`` is gated by ``X-API-Key`` because it invokes the ML
#     model and can be costly (up to 64x64 = 4096 inferences per call).
#   * All four never return silent 0.5 — model errors surface as 500 with
#     the underlying message (AGENTS.md §3 + bug #3).
#
# Lazy import of ``src.geo.services`` is done at module-load via the import
# below — that module itself lazy-imports shapely/geopandas only when the
# AOI path is exercised, so importing it here is cheap and sandbox-safe.
# ---------------------------------------------------------------------------
from src.geo import services as _geo_services  # noqa: E402 — after app/limiter


@app.get("/geo/locations")
@limiter.limit("30/minute")
async def geo_locations(request: Request):
    """Return the Indonesia city registry as a flat list (PLAN §3).

    Public-read (no API key) so the SPA sidebar combobox works on hosted
    demos. Response shape::

        [{"id": "abiageh", "name": "Abiageh", "lat": -4.48, "lon": 138.87}, ...]
    """
    entries = _geo_services.load_locations()
    if not entries:
        # Empty list is a valid outcome (file missing) but we still return
        # 200 + empty array so the SPA renders an empty-state combobox
        # rather than an error toast. Tests assert 200 + list.
        return {"count": 0, "locations": []}
    return {"count": len(entries), "locations": entries}


@app.get("/geo/geocode")
@limiter.limit("30/minute")
async def geo_geocode(
    request: Request,
    q: str = "",
):
    """Resolve a free-text query to ``{name, lat, lon, source}``.

    Tier-1: ``data/locations.json`` substring match.
    Tier-2: OSM Nominatim (1 req/sec upstream cap respected by the SPA).

    Returns 404 when both tiers miss — the SPA shows "no match" in the
    search box. Returns 400 when ``q`` is empty/whitespace (Pydantic-free
    explicit check — catches a querystring that decodes to "").
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query string 'q' is required.")
    hit = _geo_services.geocode(query)
    if hit is None:
        raise HTTPException(status_code=404, detail=f"No match for query: {query!r}")
    return hit


@app.get("/analytics/trend")
@limiter.limit("30/minute")
async def analytics_trend(
    request: Request,
    lat: float = 0.0,
    lon: float = 0.0,
    days: int = 7,
    radius_km: float = 25.0,
):
    """Per-day fire-risk trend for the (lat, lon) neighbourhood (PLAN §3).

    Reads the inference-ready features CSV (``config.paths.processed_features_path``)
    via an mtime-aware in-process cache so a regenerated CSV is picked up
    without a worker restart. ``days`` is clamped to ``[1, 90]``.

    Returns 404 when the underlying CSV is missing on disk (the SPA shows
    an empty-state chart); otherwise::

        {"lat": ..., "lon": ..., "radius_km": 25.0, "days": 7,
         "series": [{"date": "YYYY-MM-DD", "fire_rate": 0.12,
                     "p10": 0.05, "p50": 0.18, "p90": 0.42, "count": 24}]}
    """
    if not (-90.0 <= lat <= 90.0):
        raise HTTPException(status_code=400, detail="lat must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise HTTPException(status_code=400, detail="lon must be in [-180, 180]")
    try:
        result = _geo_services.get_trend_series(
            lat=float(lat), lon=float(lon), days=int(days), radius_km=float(radius_km)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


class AoiPolygonRequest(BaseModel):
    """Body for ``POST /predict/aoi`` (PLAN §3)."""

    geojson: dict = Field(
        ...,
        description="A GeoJSON Polygon, MultiPolygon, or Feature whose geometry is a Polygon.",
    )
    grid_size: int = Field(default=8, ge=1, le=64, description="Points per axis (grid_size**2 total).")
    base_features: dict = Field(
        default_factory=dict,
        description="Inference features (temperature/humidity/wind_speed/rainfall/...) applied "
        "to every grid cell; latitude/longitude come from the grid point.",
    )
    model_version: str | None = Field(default=None, description="Optional active-model override.")
    model_type: str = Field(default="new", description="'new' (stacking) or 'legacy'.")


@app.post("/predict/aoi")
@limiter.limit("10/minute")
async def predict_aoi(
    request: Request,
    payload: AoiPolygonRequest,
    api_key: str = Depends(get_api_key),
):
    """Run a batch fire-risk prediction over a grid covering an AOI polygon.

    Auth: ``X-API-Key`` (same gate as ``/predict`` — batch is expensive).
    Rate-limit: 10/min per IP (PLAN §3 implicit — model invocation).

    Returns one ``predict_fire_risk`` result dict per grid cell, augmented
    with ``lat``/``lon``/``row``/``col`` so the SPA scatter-heatmap renders
    deterministically. Per-cell failures (e.g. transient model error) are
    flagged ``status: "error"`` instead of dropping the whole batch — see
    ``services.run_aoi_batch`` for the no-silent-0.5 rationale.
    """
    try:
        points = _geo_services.build_aoi_grid(payload.geojson, grid_size=payload.grid_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not points:
        raise HTTPException(status_code=400, detail="AOI geometry produced an empty grid.")

    results = _geo_services.run_aoi_batch(
        points=points,
        base_features=payload.base_features,
        model_version=payload.model_version,
        model_type=payload.model_type,
    )
    # A result is "ok" when its status is NOT "error". predict_fire_risk uses
    # ``status="success"``; run_aoi_batch flags per-cell failures with
    # ``status="error"`` (see services.py). Counting by exclusion keeps the
    # endpoint robust to future status-string changes downstream.
    err = sum(1 for r in results if r.get("status") == "error")
    ok = len(results) - err
    return {
        "count": len(results),
        "ok": ok,
        "errors": err,
        "grid_size": payload.grid_size,
        "results": results,
    }


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
