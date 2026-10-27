from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api import models
from src.auth import get_api_key

try:  # optional dependency — see AGENTS.md §6
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    _HAS_SLOWAPI = True
except ImportError:  # pragma: no cover - sandbox without slowapi
    _HAS_SLOWAPI = False

    class _NoopLimiter:
        """Stand-in limiter when slowapi is unavailable (rate limit disabled)."""

        def limit(self, *_args, **_kwargs):
            def decorator(func):
                return func

            return decorator


logger = logging.getLogger(__name__)


# --- Authentication ---
# All protected routes use ``get_api_key`` from :mod:`src.auth`, which owns
# the placeholder blacklist and constant-time comparison.

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

# --- Rate limiting ---
# slowapi is optional: without the wheel the app still serves requests, just
# without per-IP caps (AGENTS.md §6). When it is installed, register the 429
# handler so exceeding a limit returns 429 instead of an unhandled 500.
limiter = Limiter(key_func=get_remote_address) if _HAS_SLOWAPI else _NoopLimiter()
app.state.limiter = limiter
if _HAS_SLOWAPI:
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
# Same-origin SPA traffic needs no CORS. Set ALLOWED_ORIGINS only for
# additional browser clients. A wildcard cannot be combined with credentials
# (CORS spec), so credentials are disabled in that case.
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8000,http://localhost:7860",
    ).split(",")
    if origin.strip()
]
_allow_all_origins = "*" in _ALLOWED_ORIGINS
if _allow_all_origins:
    logger.warning(
        "ALLOWED_ORIGINS='*' disables credentialed CORS; set explicit origins in production."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=not _allow_all_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
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
#   * Rate-limit 30/minute per IP (PLAN §3 "Panduan API" cap for /predict).
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
    Required keys match its ``required_keys`` list; optional keys (spectral
    bands, vegetation class) are filled from GEE when available. Range
    constraints reject physically impossible input with 422 instead of
    letting a math error surface as 500.
    """

    temperature: float = Field(..., ge=-90, le=60, description="Air temperature (°C)")
    humidity: float = Field(..., gt=0, le=100, description="Relative humidity (%)")
    wind_speed: float = Field(..., ge=0, le=100, description="Wind speed (m/s)")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (WGS84)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude (WGS84)")
    wind_direction: float | None = Field(
        default=None, ge=0, le=360, description="Wind direction (deg from N)"
    )
    rainfall: float | None = Field(default=None, ge=0, le=2000, description="Rainfall (mm)")
    ndvi: float | None = Field(
        default=None,
        ge=-1,
        le=1,
        description="Normalised Difference Vegetation Index (−1..1)",
    )
    vegetation_type: str | None = Field(default=None, description="Vegetation class")
    fuel_moisture: float | None = Field(
        default=None, ge=0, le=100, description="Fuel moisture content (%)"
    )
    model_version: str | None = Field(
        default=None,
        description="Optional model version id. Defaults to registry active version.",
    )
    model_type: Literal["new", "legacy"] = Field(
        default="new",
        description="'new' (V4.2 stack) or 'legacy' (CNN+LGBM). Default 'new'.",
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
    """Return the Indonesia city registry (PLAN §3).

    Public-read (no API key) so the SPA sidebar combobox works on hosted
    demos. Response shape::

        {"count": 378, "locations": [
            {"id": "abiageh", "name": "Abiageh", "lat": -4.48, "lon": 138.87}, ...
        ]}
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
    grid_size: int = Field(
        default=8, ge=1, le=64, description="Points per axis (grid_size**2 total)."
    )
    base_features: dict = Field(
        default_factory=dict,
        description="Inference features (temperature/humidity/wind_speed/rainfall/...) applied "
        "to every grid cell; latitude/longitude come from the grid point.",
    )
    model_version: str | None = Field(default=None, description="Optional active-model override.")
    model_type: Literal["new", "legacy"] = Field(
        default="new", description="'new' (V4.2 stack) or 'legacy' (CNN+LGBM)."
    )


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
    """Clear the in-process prediction cache.

    Model artifacts are re-read on every prediction request (no module-level
    model cache), so only the TTL prediction cache needs invalidating after a
    bundle swap or registry activation.
    """
    try:
        from src.cache import cache_clear as _clear_pred_cache

        cleared = int(_clear_pred_cache())
    except Exception as exc:  # pragma: no cover - cache is optional
        logger.debug("prediction cache invalidation skipped: %s", exc)
        cleared = 0
    return {"status": "ok", "cleared": {"prediction_cache": cleared}}


@app.get("/admin/cache/stats")
@limiter.limit("30/minute")
async def admin_cache_stats(request: Request, api_key: str = Depends(get_api_key)):
    """Return a bounded snapshot of the prediction cache for dashboards."""
    try:
        from src.cache import cache_stats as _pred_stats

        stats = _pred_stats()
    except Exception as exc:  # pragma: no cover - cache is optional
        logger.debug("prediction cache stats skipped: %s", exc)
        stats = {"enabled": False}
    return {"status": "ok", "stats": {"prediction_cache": stats}}


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
