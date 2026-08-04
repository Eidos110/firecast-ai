#!/usr/bin/env python3
"""Single-service launcher for FireCast (HF Spaces / Render / any uvicorn host).

Serves BOTH:
  - the FastAPI backend (``src.geo_api:app``) at the API routes
  - the compiled React SPA from ``frontend_react/build`` at ``/``

SPA fallback: any non-API GET request that does not match a static asset falls
back to ``index.html`` (history-mode client routing).

Auto-enables ``ENABLE_DEMO_MODE`` when the legacy model bundle is missing, so a
fresh deploy still boots without ``models/*.pth|.pkl`` files present.

Works regardless of checkout path (``/app`` or repo root). No hardcoded absolute
paths — ``HERE`` resolves from this file's location.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = HERE / "models"
STATIC_DIR = HERE / "frontend_react" / "build"

os.makedirs(DEFAULT_MODEL, exist_ok=True)
os.makedirs(HERE / "data", exist_ok=True)

# Demo-mode heuristic: also check the new stacking-model bundle so a deploy of
# just ``add_new_model/{lgb,xgb}_model.pkl`` is treated as "models present".
LEGACY_BUNDLE = ["cnn_best.pth", "lgbm_best.pkl", "scaler.pkl", "ensemble_threshold.pkl"]
NEW_BUNDLE = ["lgb_model.pkl", "xgb_model.pkl"]
model_missing = all(not (DEFAULT_MODEL / m).exists() for m in LEGACY_BUNDLE) and all(
    not (HERE / "add_new_model" / m).exists() for m in NEW_BUNDLE
)
os.environ.setdefault("ENABLE_DEMO_MODE", "true" if model_missing else "false")

for candidate in [HERE, HERE.parent, Path("/app")]:
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)
os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", os.pathsep.join(sys.path))

import uvicorn  # noqa: E402

from src.geo_api import app  # noqa: E402
from src.geo_api_spa import mount_spa  # noqa: E402

# Mount the SPA only when the build directory exists. In dev (``npm run dev``)
# Vite serves the SPA itself and proxies API calls here; mounting is a no-op
# so a missing build never blocks backend fixes.
mount_spa(app, STATIC_DIR)

port = int(os.environ.get("PORT", os.environ.get("API_PORT", "7860")))
host = os.environ.get("HOST", "0.0.0.0")
uvicorn.run(
    app,
    host=host,
    port=port,
    timeout_keep_alive=30,
    log_level="info",
)
