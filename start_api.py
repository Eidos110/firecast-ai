#!/usr/bin/env python3
"""Self-contained API launcher for Render.

Works no matter whether Render checks out the repo at /app or at the default
build working directory. Avoids hardcoded absolute paths so this file can
safely live in the repo root and still be invoked as `python /app/start_api.py`.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = HERE / "models"

os.makedirs(DEFAULT_MODEL, exist_ok=True)
os.makedirs(HERE / "data", exist_ok=True)

MODEL_MISSING = any(
    not (DEFAULT_MODEL / model).exists()
    for model in ["cnn_best.pth", "lgbm_best.pkl", "scaler.pkl", "ensemble_threshold.pkl"]
)
os.environ["ENABLE_DEMO_MODE"] = "true" if MODEL_MISSING else "false"

for candidate in [HERE, HERE.parent, Path("/app")]:
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)
os.environ["PYTHONPATH"] = os.pathsep.join(sys.path)

import uvicorn  # noqa: E402
from src.geo_api import app  # noqa: E402

port = int(os.environ.get("PORT", os.environ.get("API_PORT", "8000")))
uvicorn.run(
    app,
    host="0.0.0.0",
    port=port,
    timeout_keep_alive=30,
    log_level="info",
)
