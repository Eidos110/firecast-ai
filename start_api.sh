#!/bin/bash
# FireCast API Startup Script for Render.com
# =============================================================================

set -e

echo "========================================"
echo " FireCast API - Render Startup"
echo "========================================"

# Ensure required directories exist
mkdir -p /app/models
mkdir -p /app/data

# Check model files
MODEL_MISSING=0
for model in cnn_best.pth lgbm_best.pkl scaler.pkl ensemble_threshold.pkl; do
    if [ ! -f "/app/models/$model" ]; then
        echo "WARNING: /app/models/$model not found"
        MODEL_MISSING=1
    fi
done

if [ "$MODEL_MISSING" -eq 1 ]; then
    echo "WARNING: Some model files missing. Enabling DEMO mode."
    export ENABLE_DEMO_MODE=true
else
    echo "All model files present."
    export ENABLE_DEMO_MODE=false
fi

# Ensure PYTHONPATH
export PYTHONPATH=/app

echo "Starting uvicorn on port $PORT..."
exec uvicorn src.geo_api:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info \
    --proxy-headers \
    --forwarded-allow-ips '*'
