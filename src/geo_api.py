from __future__ import annotations
import logging
import os
import threading
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from pathlib import Path
import pandas as pd
import h3
import numpy as np
from sklearn.cluster import DBSCAN
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import List, Optional, Tuple

from src import config
from src.models import registry
from src.api import models

logger = logging.getLogger(__name__)

# --- Authentication ---
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Validate API key from header."""
    expected_key = config.get_config().api.secret_key
    if expected_key is None:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API_SECRET_KEY not set."
        )
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide X-API-Key header."
        )
    return api_key

# Global progress tracking
from collections import deque

precompute_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "message": "",
    "last_completed": deque(maxlen=100),  # Bounded to prevent memory leak
}
scheduler = AsyncIOScheduler()

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed_firecast_features_v3.csv"

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
import threading

class _DataCache:
    """Thread-safe in-memory CSV cache with mtime-based invalidation."""

    def __init__(self):
        self._df: Optional[pd.DataFrame] = None
        self._columns: Optional[dict] = None
        self._mtime: float = 0.0
        self._lock = threading.RLock()

    def _detect_columns(self, df: pd.DataFrame) -> dict:
        lat_col = next((c for c in LAT_CANDIDATES if c in df.columns), None)
        lon_col = next((c for c in LON_CANDIDATES if c in df.columns), None)
        prob_col = next((c for c in PROB_CANDIDATES if c in df.columns), None)
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        return {"lat": lat_col, "lon": lon_col, "prob": prob_col, "time": time_col}

    def get(self) -> Tuple[pd.DataFrame, dict]:
        """Return cached DataFrame and detected columns, reloading if file changed."""
        with self._lock:
            try:
                current_mtime = os.path.getmtime(DATA_PATH)
            except OSError:
                raise HTTPException(
                    status_code=404, detail=f"Data not found at {DATA_PATH}"
                )

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


def _get_cached_data() -> Tuple[pd.DataFrame, dict]:
    """Convenience wrapper to get cached data + columns."""
    df, cols = _data_cache.get()
    if cols["lat"] is None or cols["lon"] is None:
        raise HTTPException(
            status_code=400, detail="Latitude/longitude columns not found in dataset"
        )
    return df, cols


# --- Vectorized H3 helpers ---
def _h3_index_vectorized(
    lats: np.ndarray, lons: np.ndarray, resolution: int
) -> np.ndarray:
    """Compute H3 indices using list comprehension (faster than df.apply)."""
    return np.array(
        [h3.geo_to_h3(lat, lon, resolution) for lat, lon in zip(lats, lons)]
    )


def _build_hex_record(hid: str, count: int, avg_prob: Optional[float]) -> dict:
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
    # Limit request body size to 10MB to prevent memory exhaustion
    max_body_size=10 * 1024 * 1024,  # 10MB
)

# --- Rate Limiting ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# --- CORS ---
# Load allowed origins from environment or use defaults for development
import os

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8501,http://localhost:3000,http://localhost:8000"
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
from fastapi import Depends
app.include_router(
    models.router,
    prefix="/api/models",
    tags=["models"],
    dependencies=[Depends(limiter.limit("10/minute"))]  # Rate limit: 10 requests per minute per IP
)


# --- Health check ---
@app.get("/health")
@limiter.limit("120/minute")
async def health(request: Request):
    return {"status": "ok"}


# --- Cached precomputed hex file reader ---
@lru_cache(maxsize=16)
def _load_precomputed_hex(resolution: int) -> Optional[str]:
    """Load precomputed hex JSON file, cached in memory. Returns JSON string or None."""
    path = ROOT / "data" / f"hexagons_res_{resolution}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _invalidate_hex_cache():
    """Clear the precomputed hex cache."""
    _load_precomputed_hex.cache_clear()


@app.get("/precompute_progress")
@limiter.limit("60/minute")
async def get_precompute_progress(request: Request, api_key: str = Depends(get_api_key)):
    """Get current precompute progress. Requires authentication."""
    # Convert deque to list for JSON serialization
    progress_copy = precompute_progress.copy()
    progress_copy["last_completed"] = list(precompute_progress["last_completed"])
    return progress_copy
