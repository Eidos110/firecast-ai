#!/usr/bin/env python3
"""Single-service launcher for FireCast (HF Spaces / Render / any uvicorn host).

Serves BOTH:
  - the FastAPI backend (``src.geo_api:app``) at the API routes
  - the compiled React SPA from ``frontend_react/build`` at ``/``

SPA fallback: any non-API GET request that does not match a static asset falls
back to ``index.html`` (history-mode client routing).

Works regardless of checkout path (``/app`` or repo root). No hardcoded absolute
paths — ``HERE`` resolves from this file's location.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "frontend_react" / "build"

# Model/data directories are mounted at runtime on most hosts; creating them
# here keeps first boot on a fresh volume from failing at request time.
os.makedirs(HERE / "models", exist_ok=True)
os.makedirs(HERE / "data", exist_ok=True)

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
