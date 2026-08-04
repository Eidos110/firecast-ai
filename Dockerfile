# =====================================================================
# FireCast — Multi-stage Dockerfile (HF Spaces / Render / any uvicorn host)
# =====================================================================
# Stage 0 (spa-build)  : Node 20 builds the React SPA (Vite) -> frontend_react/build
# Stage 1 (base)       : Python 3.12-slim + pip install + app source + SPA copy
# =====================================================================

# ---------------------------------------------------------------------------
# Stage 0 — React SPA build
# ---------------------------------------------------------------------------
FROM node:20-slim AS spa-build

WORKDIR /spa

# Copy manifest first for npm ci caching layer (lockfile + package.json only).
COPY frontend_react/package.json frontend_react/package-lock.json* ./

# Install deps. `npm ci` requires a lockfile; fall back to `npm install` if the
# consumer shipped the repo without package-lock.json (rare on CI, common on
# hand-zips). Keep the fallback silent so CI logs stay clean.
RUN if [ -f package-lock.json ]; then \
      npm ci --no-audit --no-fund; \
    else \
      npm install --no-audit --no-fund; \
    fi

# Copy the rest of the React sources + Vite config + tsconfig + tailwind.
COPY frontend_react/ ./

# Build the SPA. `tsc --noEmit && vite build` runs in package.json "build".
# We expose the build directory with Vite's `build.outDir: build` config.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 1 — Python runtime (base target, used by render.yaml / docker-compose)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python dependencies — install first for layer caching
# ---------------------------------------------------------------------------
COPY requirements.txt ./

# CPU-only PyTorch keeps the image ~700 MB smaller than the CUDA build and
# matches the FIREvCPU training env (pickle version parity).
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# ---------------------------------------------------------------------------
# Application source
# ---------------------------------------------------------------------------
COPY . .

# Use the sample CSV fallback if the real processed features file is absent
# (Hugging Face Spaces ships without the heavy dataset).
RUN mkdir -p /app/models /app/data && \
    if [ -f /app/data/sample_data_hf.csv ] && \
       [ ! -f /app/data/processed_firecast_features_v3.csv ]; then \
        cp /app/data/sample_data_hf.csv /app/data/processed_firecast_features_v3.csv; \
        echo "[FireCast] Using sample data for Hugging Face Spaces"; \
    fi

# ---------------------------------------------------------------------------
# Copy the React SPA build produced in stage 0
# ---------------------------------------------------------------------------
COPY --from=spa-build /spa/build /app/frontend_react/build

# ---------------------------------------------------------------------------
# Environment defaults (override at runtime)
# ---------------------------------------------------------------------------
ENV PYTHONPATH=/app \
    PORT=7860 \
    HOST=0.0.0.0 \
    ENABLE_DEMO_MODE=true \
    ML_DEVICE=cpu \
    ENABLE_CORS=true \
    ALLOWED_ORIGINS="*"

EXPOSE 7860

# ---------------------------------------------------------------------------
# Healthcheck — FastAPI /health endpoint (single-process model). The SPA is
# served by the same uvicorn worker, so /health covers both.
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# ---------------------------------------------------------------------------
# Entrypoint — single uvicorn process serving API + SPA
# ---------------------------------------------------------------------------
CMD ["python", "start_api.py"]
