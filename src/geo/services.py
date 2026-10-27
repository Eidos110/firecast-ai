"""Geo service helpers for the FireCast Geo API (Tahap B).

This module is the single backend implementation of the geo/AOI helpers.
The old Streamlit-era ``frontend/utils`` copies were removed after the React
SPA migration:

* ``get_trend_series`` — per-day risk trend, memoised by file mtime.
* ``build_aoi_grid`` + ``run_aoi_batch`` — GeoJSON polygon → grid → batch
  predictions for the SPA heatmap.
* ``load_locations`` / ``geocode`` — Indonesia city registry + Nominatim
  fallback for the sidebar search.

Nothing here imports Streamlit.

Design rules (from PLAN.md §1 + AGENTS.md §3):

* NEVER return silent 0.5 on model error — raise → 500 PredictionError.
* Single source of truth for paths via ``config.paths``.
* Lazy import optional deps (geopandas/shapely) — sandbox-safe.
* No Streamlit imports anywhere.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# locations.json loader
# ---------------------------------------------------------------------------

# Cache keyed by (path, mtime) so an operator that swaps the file on disk
# (``/admin/cache/invalidate`` → file regen) still sees fresh entries without
# restarting the worker. Tuples are hashable; mtime comes from os.stat.
_LOCATIONS_CACHE: tuple[float, list[dict]] | None = None


def locations_path() -> Path:
    """Return the resolved path to ``data/locations.json`` via config."""
    return config.get_config().paths.locations_path


def load_locations() -> list[dict]:
    """Load ``data/locations.json`` and return it as a flat list of points.

    File format (see ``data/locations.json``): ``{key: {name, lat, lon}}``.
    Response shape (kept stable for the SPA sidebar):

        [{"id": "abiageh", "name": "Abiageh", "lat": -4.48, "lon": 138.87}, ...]

    The list is sorted by ``name`` (case-insensitive) so the React combobox
    renders deterministic results. On error returns an empty list — the
    endpoints surface 404 when the file is missing so the SPA can show a
    graceful "no locations" empty-state instead of crashing.
    """
    global _LOCATIONS_CACHE
    path = locations_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        # File missing → reset cache, return empty. Caller (endpoint) decides
        # whether to raise 404 or serve a partial response.
        _LOCATIONS_CACHE = None
        return []

    if _LOCATIONS_CACHE is not None and _LOCATIONS_CACHE[0] == mtime:
        return _LOCATIONS_CACHE[1]

    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("load_locations: failed reading %s: %s", path, exc)
        _LOCATIONS_CACHE = None
        return []

    if not isinstance(raw, dict):
        logger.warning("load_locations: %s is not a dict; got %s", path, type(raw).__name__)
        _LOCATIONS_CACHE = None
        return []

    entries: list[dict] = []
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        try:
            lat = float(val.get("lat"))
            lon = float(val.get("lon"))
        except (TypeError, ValueError):
            continue
        name = str(val.get("name", key))
        entries.append({"id": str(key), "name": name, "lat": lat, "lon": lon})

    entries.sort(key=lambda e: e["name"].lower())
    _LOCATIONS_CACHE = (mtime, entries)
    return entries


# ---------------------------------------------------------------------------
# Geocode
# ---------------------------------------------------------------------------

# Placeholder-strings for the optional upstream endpoint. Mirrors the
# ``auth._PLACEHOLDER_API_KEYS`` pattern so a forgotten .env copy does not
# silently make geocode "look" upstream-queryable.
_NOMINATIM_PLACEHOLDER_HEADERS = frozenset({"", "changeme", "demo_key"})


def _local_geocode(query: str) -> dict | None:
    """Tier-1: case-insensitive substring match against ``data/locations.json``.

    Returns the first match as ``{"name", "lat", "lon", "source": "local"}``
    or ``None`` when no local entry matches.

    Matching policy: match if ``query`` appears inside the location's
    ``name`` (case-insensitive) OR equals its ``id``. Substring keeps the UX
    forgiving (user types "ace" → first "Aceh" wins) while equality on ``id``
    lets the SPA replay an exact selection deterministically.
    """
    q = (query or "").strip().lower()
    if not q:
        return None
    for entry in load_locations():
        if q == entry["id"].lower() or q == entry["name"].lower():
            return {
                "name": entry["name"],
                "lat": entry["lat"],
                "lon": entry["lon"],
                "source": "local",
            }
    for entry in load_locations():
        if q in entry["name"].lower():
            return {
                "name": entry["name"],
                "lat": entry["lat"],
                "lon": entry["lon"],
                "source": "local",
            }
    return None


def _nominatim_geocode(query: str, timeout: float = 5.0) -> dict | None:
    """Tier-2: ask OpenStreetMap Nominatim when Tier-1 misses.

    Respects Nominatim usage policy:
      * ``format=json`` + ``limit=1`` (single result).
      * A descriptive ``User-Agent`` (default ``FireCast-Geo/1.0``,
        override with env ``NOMINATIM_USER_AGENT``).
      * Bounded timeout so a slow upstream never blocks the API worker.

    Disabled (returns ``None``) when:
      * ``urllib`` fails to import (sandbox),
      * the network request raises / times out,
      * Nominatim returns an empty / malformed list.

    Intentionally NOT rate-limited here — the public Nominatim instance
    expects ≤1 req/sec per app, so the SPA should prefer Tier-1 and only
    fall back to Tier-2 on user-initiated "search not in list" action. The
    endpoint itself is rate-limited at the FastAPI layer (see geo_api.py).
    """
    import urllib.parse
    import urllib.request

    user_agent = os.environ.get("NOMINATIM_USER_AGENT", "FireCast-Geo/1.0")
    if user_agent in _NOMINATIM_PLACEHOLDER_HEADERS:
        return None

    q = (query or "").strip()
    if not q:
        return None

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1, "countrycodes": "id"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # broad: network/timeout/json errors
        logger.info("Nominatim geocode failed for %r: %s", q, exc)
        return None

    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    try:
        return {
            "name": str(first.get("display_name", q)).split(",")[0].strip(),
            "lat": float(first.get("lat")),
            "lon": float(first.get("lon")),
            "source": "nominatim",
        }
    except (TypeError, ValueError):
        return None


def geocode(query: str) -> dict | None:
    """Resolve a free-text query to ``{name, lat, lon, source}``.

    Strategy: Tier-1 local JSON, Tier-2 Nominatim. Never raises — returns
    ``None`` when both tiers fail so the endpoint can respond with a clean
    404 instead of a 500.
    """
    hit = _local_geocode(query)
    if hit is not None:
        return hit
    return _nominatim_geocode(query)


# ---------------------------------------------------------------------------
# Trend — port of analytics.get_monthly_fire_data / get_filtered_data,
# stripped of Streamlit cache. We serve a 7-day rolling-window time series
# for one (lat, lon) cell instead of monthly aggregates, which is what the
# RightDiagnostic "RiskTrendChart" (PLAN §2) actually wants.
# ---------------------------------------------------------------------------


def trend_csv_path() -> Path:
    """The inference-ready features CSV used for trend aggregation.

    Same path as ``geo_api.py:DATA_PATH`` so /analytics/trend and the map
    hex layer read a consistent SKU.
    """
    return config.get_config().paths.processed_features_path


@lru_cache(maxsize=8)
def _trend_load_df(path_str: str, mtime: float) -> pd.DataFrame | None:
    """Load the trend CSV once per (path, mtime) — fresh on file change.

    ``lru_cache`` keys on the resolved str path AND the file mtime so an
    operator that regenerates the CSV (config.paths processed_features_path)
    immediately invalidates the cache without a worker restart.
    """
    try:
        df = pd.read_csv(path_str)
    except Exception as exc:  # pragma: no cover — depends on env
        logger.warning("trend CSV read failed (%s): %s", path_str, exc)
        return None
    # Detect & parse the time column (mirrors geo_api.TIME_CANDIDATES).
    time_col = next((c for c in ("time", "timestamp", "datetime", "date") if c in df.columns), None)
    if time_col is not None:
        df["time"] = pd.to_datetime(df[time_col], errors="coerce")
    return df


def _trend_get_df() -> pd.DataFrame:
    """Resolve & load the trend DataFrame (mtime-aware, sandbox-safe)."""
    path = trend_csv_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError as exc:
        raise FileNotFoundError(f"Trend CSV not found at {path}: {exc}") from exc
    return _trend_load_df(str(path), mtime)


def _trend_compute(
    lat: float,
    lon: float,
    days: int,
    radius_km: float,
) -> dict[str, Any]:
    """Compute the trend series from the cached DataFrame.

    Has no caching of its own — callers should go through
    :func:`_trend_series_cached` for the full mtime-keyed memo.
    """
    df = _trend_get_df()
    if df is None or len(df) == 0:
        return {"lat": lat, "lon": lon, "radius_km": radius_km, "days": days, "series": []}

    lat_col = next(
        (c for c in ("lat", "latitude", "Latitude", "LAT", "lat_deg") if c in df.columns), None
    )
    lon_col = next(
        (c for c in ("lon", "longitude", "Longitude", "LON", "lon_deg") if c in df.columns), None
    )
    if lat_col is None or lon_col is None:
        return {"lat": lat, "lon": lon, "radius_km": radius_km, "days": days, "series": []}

    prob_col = next(
        (
            c
            for c in ("probability", "prob", "pred_prob", "score", "fire_prob", "probability_fire")
            if c in df.columns
        ),
        None,
    )

    # Optional spatial filter (haversine). Radius 0 → exact-match fast path.
    if radius_km > 0:
        # Earth radius in km; vectorised haversine.
        r = 6371.0
        lat_rad = np.radians(df[lat_col].astype(float).values)
        lon_rad = np.radians(df[lon_col].astype(float).values)
        tlat = math.radians(lat)
        tlon = math.radians(lon)
        dlat = lat_rad - tlat
        dlon = lon_rad - tlon
        a = np.sin(dlat / 2) ** 2 + np.cos(lat_rad) * math.cos(tlat) * np.sin(dlon / 2) ** 2
        dist = 2 * r * np.arcsin(np.sqrt(a))
        mask = dist <= radius_km
    else:
        mask = (df[lat_col].astype(float) == float(lat)) & (df[lon_col].astype(float) == float(lon))

    sub = df.loc[mask].copy()
    if len(sub) == 0:
        return {"lat": lat, "lon": lon, "radius_km": radius_km, "days": days, "series": []}

    if "time" not in sub.columns or sub["time"].isna().all():
        return {"lat": lat, "lon": lon, "radius_km": radius_km, "days": days, "series": []}

    # Trailing window from the CSV's latest timestamp backwards by ``days``.
    latest = sub["time"].max()
    start = latest - pd.Timedelta(days=days)
    sub = sub[sub["time"] >= start].copy()
    if len(sub) == 0:
        return {"lat": lat, "lon": lon, "radius_km": radius_km, "days": days, "series": []}

    sub["day"] = sub["time"].dt.floor("D")
    if prob_col and prob_col in sub.columns:
        prob_values = sub[prob_col].astype(float)
    elif "label" in sub.columns:
        prob_values = sub["label"].astype(float)
    else:
        # No score column at all: the row-index default MUST reuse ``sub``'s
        # index, otherwise ``prob_values.loc[grp.index]`` raises KeyError for
        # every row after the first group.
        prob_values = pd.Series(0.0, index=sub.index)

    grouped = sub.groupby("day")
    series: list[dict[str, Any]] = []
    for day, grp in grouped:
        probs = prob_values.loc[grp.index]
        if probs.empty:
            continue
        q = np.nanquantile(probs.values, [0.1, 0.5, 0.9]).tolist()
        if "label" in grp.columns:
            fire_rate = float(pd.to_numeric(grp["label"], errors="coerce").fillna(0).mean())
        else:
            fire_rate = float(probs.mean())
        series.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "fire_rate": round(fire_rate, 4),
                "p10": round(q[0], 4),
                "p50": round(q[1], 4),
                "p90": round(q[2], 4),
                "count": int(len(grp)),
            }
        )
    series.sort(key=lambda e: e["date"])
    return {"lat": lat, "lon": lon, "radius_km": radius_km, "days": days, "series": series}


@lru_cache(maxsize=128)
def _trend_series_cached(
    lat: float,
    lon: float,
    days: int,
    radius_km: float,
    mtime: float,
) -> dict[str, Any]:
    """Mtime-keyed memo wrapper around ``_trend_compute`` (ROADMAP §2-J).

    The full haversine + groupby pipeline costs ~50–100 ms on the
    processed_features CSV. Caching the final dict by
    ``(lat, lon, days, radius_km, mtime)`` collapses repeat requests
    (engineers scrubbing the timeline back and forth) to a dict-return hit.
    The ``mtime`` part of the key is the invalidation strategy: when the
    operator regenerates the CSV, its mtime changes → the lru_cache evicts
    the stale entries naturally without needing an explicit purge hook.
    """
    return _trend_compute(lat, lon, days, radius_km)


def get_trend_series(
    lat: float,
    lon: float,
    days: int = 7,
    radius_km: float = 25.0,
) -> dict[str, Any]:
    """Return a per-day fire-risk trend for the (lat, lon) neighbourhood.

    Aggregation:
      1. Filter CSV rows whose (lat, lon) are within ``radius_km`` of the
         target (great-circle distance via the haversine formula on the
         lat/lon columns auto-detected by ``geo_api`` LAT/LON_CANDIDATES).
      2. Bucket by calendar day.
      3. For each day compute:
           * ``fire_rate``  — fraction of rows with ``label == 1``.
           * ``p10``/``p50``/``p90`` — quantiles of any probability column
             detected by ``geo_api.PROB_CANDIDATES`` (e.g. ``probability``).
             If absent, fall back to ``label`` so the chart still renders.
           * ``count`` — number of rows in the bucket.

    Args:
        lat, lon: target cell.
        days: trailing window in days (default 7 per PLAN §3). Clamped to
            ``[1, 90]`` to bound the response size.
        radius_km: neighbourhood radius in km (default 25 — roughly a single
            H3 res-7 cell). 0 is legal and means "exact lat/lon match".

    Returns:
        ``{"lat", "lon", "radius_km", "days", "series": [{date, fire_rate,
        p10, p50, p90, count}, ...]}``. Empty ``series`` when the cell has
        no nearby rows (the SPA renders an empty-state chart).

    Raises:
        FileNotFoundError — CSV missing (handled by the endpoint → 404).
    """
    days = max(1, min(int(days), 90))
    radius_km = max(0.0, float(radius_km))

    # Resolve the file mtime so the lru_cache key captures invalidation
    # (cache miss on regenerated CSV without worker restart).
    path = trend_csv_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError as exc:
        raise FileNotFoundError(f"Trend CSV not found at {path}: {exc}") from exc

    # Round coordinates so near-identical requests collapse into one entry.
    # 5 decimal places ≈ 1 m — tighter than the H3 res-7 cell the radius
    # implies, so we never merge two calls that would produce different
    # series. Keeps cache-size bounded on dense AOI sweeps.
    lat_key = round(float(lat), 5)
    lon_key = round(float(lon), 5)
    return _trend_series_cached(lat_key, lon_key, days, radius_km, mtime)


# ---------------------------------------------------------------------------
# AOI — grid generator + batch predict wrapper
# ---------------------------------------------------------------------------


def _bbox_of_rings(
    rings: Iterable[Iterable[tuple[float, float]]],
) -> tuple[float, float, float, float] | None:
    """Return ``(min_lat, min_lon, max_lat, max_lon)`` for a list of rings.

    Accepts GeoJSON polygon ``coordinates`` (list of rings, each a list of
    ``[lon, lat]`` pairs). Returns ``None`` for empty input.
    """
    min_lat = min_lon = math.inf
    max_lat = max_lon = -math.inf
    found = False
    for ring in rings:
        for pair in ring:
            lon = float(pair[0])
            lat = float(pair[1])
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
            found = True
    if not found:
        return None
    return (min_lat, min_lon, max_lat, max_lon)


def build_aoi_grid(geojson: dict, grid_size: int = 8) -> list[dict]:
    """Generate an evenly spaced grid of sample points over an AOI polygon.

    Args:
        geojson: a GeoJSON ``Polygon`` or ``Feature`` whose geometry is a
            Polygon. Coordinates are ``[lon, lat]`` per the GeoJSON spec.
        grid_size: number of points along each axis (``grid_size**2`` total).
            Clamped to ``[1, 64]`` — 4 096 points is a generous ceiling for
            a single batch inference call.

    Returns:
        ``[{"lat", "lon", "row", "col"}, ...]`` — column-then-row order so
        the SPA can reconstruct the 2-D heatmap when needed.

    Point-in-polygon containment is honoured when ``shapely`` is importable
    (the common case in production), and skipped (returns the full bbox
    grid) in sandboxes without it (PLAN §6 "graceful fallback" — the SPA
    already shows the AOI outline layer, so an out-of-bounds point still
    gets a prediction tagged with ``inside_aoi: false`` from the caller
    when needed).
    """
    grid_size = max(1, min(int(grid_size), 64))

    if not isinstance(geojson, dict):
        raise ValueError("geojson must be a dict")
    geom = geojson.get("geometry", geojson)
    gtype = geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon", "Feature"):
        raise ValueError(f"Unsupported geometry type: {gtype!r} (expected Polygon)")

    rings: list[list[tuple[float, float]]] = []
    if gtype == "Polygon":
        rings = [[(float(p[0]), float(p[1])) for p in ring] for ring in geom.get("coordinates", [])]
    elif gtype == "MultiPolygon":
        for poly in geom.get("coordinates", []):
            for ring in poly:
                rings.append([(float(p[0]), float(p[1])) for p in ring])
    else:  # Feature — recurse into geometry (defensive)
        return build_aoi_grid(geom.get("geometry", {}), grid_size=grid_size)

    bbox = _bbox_of_rings(rings)
    if bbox is None:
        return []
    min_lat, min_lon, max_lat, max_lon = bbox

    # Shapely containment guard (optional). When shapely is available we
    # skip grid points that fall outside the user-drawn polygon so the SPA
    # heatmap only paints cells inside the AOI. We use ``intersects`` (not
    # ``contains``) so boundary points — including bbox corners when
    # grid_size=2 — are kept (contains() rejects on-boundary points, which
    # would leave gaps along the outline). Sandbox without shapely → falls
    # back to the full bbox grid (PLAN §6 "graceful fallback"); the SPA
    # renders the AOI outline layer anyway, so an out-of-bounds point is
    # visually obvious.
    _shapely_geom = None
    try:
        from shapely.geometry import shape  # type: ignore[import-not-found]

        try:
            _shapely_geom = shape(geom)
        except Exception as exc:  # malformed geometry
            logger.debug("shapely.shape parse failed; using bbox grid: %s", exc)
            _shapely_geom = None
    except ImportError:
        _shapely_geom = None

    n = max(grid_size, 1)
    # Inclusive endpoints so user-supplied AOI corners always get sampled.
    if n == 1:
        lats = [(min_lat + max_lat) / 2]
        lons = [(min_lon + max_lon) / 2]
    else:
        lats = [min_lat + (max_lat - min_lat) * i / (n - 1) for i in range(n)]
        lons = [min_lon + (max_lon - min_lon) * i / (n - 1) for i in range(n)]

    # Lazily build the Point class once for the loop (shapely import-cached).
    _Point = None
    if _shapely_geom is not None:
        try:
            from shapely.geometry import Point as _Point  # type: ignore[import-not-found]
        except ImportError:
            _Point = None
            _shapely_geom = None

    # NOTE: ``contains()`` would reject points exactly on the polygon
    # boundary — and our grid endpoints *are* AOI corners (grid_size=2 →
    # exactly the bbox corners). Use ``intersects()`` so boundary points are
    # kept; the SPA heatmap therefore never paints "eye of fire" gaps along
    # the user-drawn outline.
    points: list[dict] = []
    for r in range(n):
        for c in range(n):
            lat = lats[r]
            lon = lons[c]
            if (
                _shapely_geom is not None
                and _Point is not None
                and not _shapely_geom.intersects(_Point(lon, lat))
            ):
                continue
            points.append({"lat": round(lat, 6), "lon": round(lon, 6), "row": r, "col": c})
    return points


def run_aoi_batch(
    points: list[dict],
    base_features: dict[str, Any],
    model_version: str | None = None,
    model_type: str = "new",
) -> list[dict]:
    """Run ``predict_fire_risk`` for every point in ``points``.

    Accepts a list of ``{"lat", "lon", ...}`` dicts and a ``base_features``
    dict (temperature/humidity/wind_speed/rainfall/...) that is merged with
    each point's lat/lon. Returns one prediction dict per point, augmented
    with ``lat``/``lon`` so the SPA can scatter-plot the batch on the map.

    Failure handling (PLAN §1 + AGENTS.md §3 — never silent 0.5):
      * A point whose prediction raises is marked
        ``{"lat", "lon", "status": "error", "error": str(exc)}`` rather than
        killing the whole batch — this preserves the user's other cells.
        A 0.5 fallback is NOT used because that would silently mask a real
        fire on the map. The SPA filters ``status == "error"`` out of the
        heatmap but shows them in the AOI table as failed cells.
      * ``/predict/aoi`` reports ``ok``/``errors`` counts so callers can see
        partial failures without inspecting every row.
    """
    if not points:
        return []

    from src.predict import PredictionError, predict_fire_risk

    out: list[dict] = []
    for pt in points:
        feats = dict(base_features)
        feats["latitude"] = float(pt["lat"])
        feats["longitude"] = float(pt["lon"])
        # Per-point override features may come in from the point dict itself.
        for k in ("temperature", "humidity", "wind_speed", "rainfall", "ndvi", "wind_direction"):
            if k in pt and pt[k] is not None:
                feats[k] = pt[k]
        started = time.perf_counter()
        try:
            result = predict_fire_risk(
                features=feats,
                model_version=model_version,
                model_type=model_type,
                use_cache=True,  # AOI batch is often a rerun with one cell changed
            )
            latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
            result["lat"] = float(pt["lat"])
            result["lon"] = float(pt["lon"])
            result.setdefault("latency_ms", latency_ms)
            result.setdefault("row", pt.get("row"))
            result.setdefault("col", pt.get("col"))
            result.setdefault("status", "ok")
            out.append(result)
        except PredictionError as exc:
            logger.warning("AOI batch point (%s) PredictionError: %s", pt, exc)
            out.append(
                {
                    "lat": float(pt["lat"]),
                    "lon": float(pt["lon"]),
                    "row": pt.get("row"),
                    "col": pt.get("col"),
                    "status": "error",
                    "error": str(exc),
                }
            )
        except Exception as exc:
            logger.exception("AOI batch unexpected error for point %s", pt)
            out.append(
                {
                    "lat": float(pt["lat"]),
                    "lon": float(pt["lon"]),
                    "row": pt.get("row"),
                    "col": pt.get("col"),
                    "status": "error",
                    "error": f"Unexpected error: {exc}",
                }
            )
    return out
