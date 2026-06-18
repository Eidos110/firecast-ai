#!/usr/bin/env python3
"""Minimal API launcher for Railway deployment.

This script sets up the Python path correctly, performs diagnostic checks,
and launches uvicorn. All diagnostic output goes to stdout and is visible in
Railway runtime logs, even after exec replaces the process.
"""
import os
import sys

# ─── Install directory (+cwd fallback so 'src.' always resolves) ───
_here = os.path.dirname(os.path.abspath(__file__))  # e.g. /app
for _p in (_here, os.getcwd()):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ["PYTHONPATH"] = _here  # also export for child processes

# ─── Diagnostics ───
print("=== start_api.py ===")
print(f"__file__={__file__}")
print(f"cwd={os.getcwd()}")
print(f"sys.argv={sys.argv}")
print(f"PORT={os.environ.get('PORT', '<not set>')}")
print(f"PYTHONPATH={os.environ.get('PYTHONPATH', '<not set>')}")
print(f"python={sys.executable} {sys.version}")
print("--- importing uvicorn ---")
import uvicorn          # noqa: E402  (stdlib print already done beforehand)
print(f"uvicorn={uvicorn.__version__}")
print("--- importing src.config ---")
from src import config  # noqa: E402  (triggers lazy torch load; prints device)
print("--- importing src.geo_api ---")
from src.geo_api import app  # noqa: E402
print("--- geo_api imported OK\n")

port = int(os.environ.get("PORT", os.environ.get("API_PORT", "8000")))
print(f"=== STARTING uvicorn on 0.0.0.0:{port} ===")
# launch uvicorn directly via its programmatic interface so
# stdout / stderr are inherited from this process
uvicorn.run(
    "src.geo_api:app",
    host="0.0.0.0",
    port=port,
    timeout_keep_alive=30,
)
