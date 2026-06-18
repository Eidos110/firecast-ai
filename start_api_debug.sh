#!/bin/bash
set -ex

echo "=== FireCast API startup $(date -u) ==="
cd /app
export PYTHONPATH=/app

echo "--- Python $(python3 --version) ---"
echo "PORT=${PORT:-<unset>}"
echo "--- Files in /app/src ---"
ls /app/src/

echo "--- Test config import ---"
python3 -c "import sys; sys.path.insert(0,'/app'); from src.config import get_config; cfg=get_config(); print('config OK:', cfg.__class__.__name__)" 2>&1 || {
  echo "!!! config import FAILED"
  python3 -c "import sys, traceback; sys.path.insert(0,'/app'); traceback.print_exc()" 2>&1
  exit 1
}

echo "--- Test geo_api import ---"
python3 -c "import sys; sys.path.insert(0,'/app'); from src.geo_api import app; print('geo_api OK')" 2>&1 || {
  echo "!!! geo_api import FAILED"
  python3 -c "import sys, traceback; sys.path.insert(0,'/app'); traceback.print_exc()" 2>&1
  exit 1
}

echo "--- Test uvicorn ---"
python3 -c "import uvicorn; print('uvicorn', uvicorn.__version__)" 2>&1 || {
  echo "!!! uvicorn import FAILED"
  exit 1
}

echo "=== ALL CHECKS PASSED - starting uvicorn $(date -u) ==="
exec uvicorn src.geo_api:app --host 0.0.0.0 --port ${PORT:-8000}
