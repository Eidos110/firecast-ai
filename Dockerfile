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

# Locale JSONs + theme tokens are the single-source-of-truth shared with the
# legacy Streamlit-era frontend (`frontend/locales/{en,id}.json`,
# `frontend/themes/tokens.json`). Two build inputs reach OUTSIDE the SPA dir:
#   - `i18n.ts` imports `../../../frontend/locales/...`  -> /frontend/locales
#   - `tailwind.config.cjs` requires `../frontend/themes/tokens.json`
#                                                       -> /frontend/themes
# Both resolve to absolute paths relative to this stage's WORKDIR /spa, so we
# COPY them to those absolute locations before `npm run build`. (Fixes HF
# Spaces build 2026-08-05: TS2307 + [vite:css] "Cannot find module
# '../frontend/themes/tokens.json'".)
COPY frontend/locales/ /frontend/locales/
COPY frontend/themes/ /frontend/themes/

# Copy the rest of the React sources + Vite config + tsconfig + tailwind.
COPY frontend_react/ ./

# Build the SPA. `tsc --noEmit && vite build` runs in package.json "build".
# We expose the build directory with Vite's `build.outDir: build` config.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 1 — Python runtime (base target used by docker-compose and HF Spaces)
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
#
# nvidia-nccl-cu12: xgboost>=3.0 declares it as a hard metadata dep on
# Linux, but the CPU inference path (`tree_method='hist'`, `device='cpu'`)
# never imports it. Uninstall it after the main install so the ~340 MB
# CUDA lib does not bloat this CPU-only image. `|| echo` keeps the build
# green when the package is absent (e.g. future xgboost drops the dep).
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt \
    && (pip uninstall -y nvidia-nccl-cu12 || echo "nvidia-nccl-cu12 not present")

# ---------------------------------------------------------------------------
# Application source
# ---------------------------------------------------------------------------
COPY . .

# Runtime data/model directories may be mounted by the host; creating them
# here keeps the first boot from failing on a fresh volume.
RUN mkdir -p /app/models /app/data

# ---------------------------------------------------------------------------
# Copy the React SPA build produced in stage 0
# ---------------------------------------------------------------------------
COPY --from=spa-build /spa/build /app/frontend_react/build

# ---------------------------------------------------------------------------
# Environment defaults (override at runtime)
#
# ALLOWED_ORIGINS is deliberately not set: the SPA is served same-origin by
# this container, and third-party browser clients should opt in explicitly at
# deploy time. Unset → src/geo_api.py uses its localhost dev allowlist.
# ---------------------------------------------------------------------------
ENV PYTHONPATH=/app \
    PORT=7860 \
    HOST=0.0.0.0 \
    ML_DEVICE=cpu

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
