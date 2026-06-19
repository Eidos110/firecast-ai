#!/usr/bin/env python3
"""Minimal API launcher for Railway deployment.

This script sets up the Python path correctly, performs diagnostic checks,
and launches uvicorn. All diagnostic output goes to stdout and is visible in
Railway runtime logs, even after exec replaces the process.
"""
import os
import sys

# Setup directories
os.makedirs("/app/models", exist_ok=True)
os.makedirs("/app/data", exist_ok=True)

# Use start_api.sh logic: check model files and set DEMO_MODE
MODEL_MISSING = 0
for model in ["cnn_best.pth", "lgbm_best.pkl", "scaler.pkl", "ensemble_threshold.pkl"]:
    if not os.path.exists(f"/app/models/{model}"):
        MODEL_MISSING = 1
        break

if MODEL_MISSING:
    os.environ["ENABLE_DEMO_MODE"] = "true"
else:
    os.environ["ENABLE_DEMO_MODE"] = "false"

# Ensure PYTHONPATH
os.environ["PYTHONPATH"] = "/app"
sys.path.insert(0, "/app")
sys.path.insert(0, os.getcwd())

import uvicorn
from src.geo_api import app

port = int(os.environ.get("PORT", os.environ.get("API_PORT", "8000")))
uvicorn.run(
    app,
    host="0.0.0.0",
    port=port,
    timeout_keep_alive=30,
    log_level="info",
)
