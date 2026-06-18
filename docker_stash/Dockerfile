# FireCast Dockerfile
# Multi-stage build for optimized production image
# =============================================================================
# Stage 0: React Frontend Builder
# =============================================================================
FROM node:18-alpine as react-builder

WORKDIR /app/frontend_react

# Copy React frontend package files
COPY frontend_react/package*.json ./

# Install Node dependencies
RUN npm ci --silent

# Copy React source code
COPY frontend_react/ ./

# Build React app (creates dist/ or build/ directory)
RUN npm run build

# =============================================================================
# Stage 1: Base Image with Dependencies
# =============================================================================
FROM python:3.9-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    # Geospatial libraries
    libproj-dev \
    libgeos-dev \
    gdal-bin \
    libgdal-dev \
    # SSL/FFI for cryptography
    libssl-dev \
    libffi-dev \
    # Image processing
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better Docker layer caching)
COPY requirements.txt requirements-frontend.txt requirements-api.txt requirements-dev.txt ./

# Replace CUDA-specific PyTorch with CPU variant for Railway/CPU-only environments
# This modifies the requirements files in the build context (not the source)
RUN if grep -q "+cu102" requirements.txt; then \
      sed -i 's/+cu102/+cpu/g' requirements.txt && \
      echo "Converted PyTorch to CPU variant"; \
    fi && \
    if grep -q "+cu102" requirements-api.txt; then \
      sed -i 's/+cu102/+cpu/g' requirements-api.txt && \
      echo "Converted API PyTorch to CPU variant"; \
    fi && \
    if grep -q "+cu102" requirements-frontend.txt; then \
      sed -i 's/+cu102/+cpu/g' requirements-frontend.txt && \
      echo "Converted Frontend PyTorch to CPU variant"; \
    fi && \
    if grep -q "+cu102" requirements-dev.txt; then \
      sed -i 's/+cu102/+cpu/g' requirements-dev.txt && \
      echo "Converted Dev PyTorch to CPU variant"; \
    fi

# =============================================================================
# Stage 2: Development Image
# =============================================================================
FROM base as development

# Install system dependencies for Node.js and building
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-frontend.txt requirements-api.txt requirements-dev.txt ./

# Install all dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    -r requirements-frontend.txt \
    -r requirements-api.txt \
    -r requirements-dev.txt

# Copy application code
COPY . .

# Build React frontend for development (watch mode not needed in container)
WORKDIR /app/frontend_react
RUN npm install && npm run build
WORKDIR /app

# Set environment
ENV PYTHONPATH=/app
ENV APP_ENV=development
ENV DEBUG=true

# Expose ports
EXPOSE 8501 8000

# Default command
CMD ["python", "launch_prototype.py", "--mode", "frontend"]

# =============================================================================
# Stage 3: Production Image (Frontend only)
# =============================================================================
FROM base as frontend

# Copy requirements
COPY requirements.txt requirements-frontend.txt ./

# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt -r requirements-frontend.txt

# Copy application code
COPY . .

# Copy built React frontend from react-builder stage
COPY --from=react-builder /app/frontend_react/build ./frontend_react/build

# Health check probes Railway's dynamic port
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f "http://localhost:${PORT:-8501}/_stcore/health" || exit 1

# Use shell-form CMD so $PORT environment variable substitution works
CMD ["sh", "-c", "streamlit run frontend/app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]

# =============================================================================
# Stage 4: Production Image (API only)
# =============================================================================
FROM base as api

# Copy requirements
COPY requirements.txt requirements-api.txt ./

# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

# Copy application code
COPY . .

# Copy built React frontend from react-builder stage (for serving static assets if needed)
COPY --from=react-builder /app/frontend_react/build ./frontend_react/build

# Port is set from Railway's $PORT env var at runtime (do NOT hardcode here)
# Railway sets $PORT dynamically; uvicorn below reads it.
# Expose common fallback so Docker knows the intent (Railway overrides internally).
EXPOSE 8000

# Use start_api.sh wrapper — pre-flight checks + exec uvicorn.
# Every echo goes to stdout so Railway captures the full runtime trace.
CMD ["sh", "-c", "/app/start_api.sh"]
