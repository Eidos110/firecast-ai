# FireCast - Hugging Face Spaces Deployment
# Based on Hugging Face Spaces recommended configuration

FROM python:3.12-slim

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
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Using CPU-only PyTorch (required for Hugging Face Spaces)
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories and copy sample data if needed
RUN mkdir -p /app/models /app/data && \
    if [ -f /app/data/sample_data_hf.csv ] && [ ! -f /app/data/processed_firecast_features_v3.csv ]; then \
        cp /app/data/sample_data_hf.csv /app/data/processed_firecast_features_v3.csv; \
        echo "Using sample data for Hugging Face Spaces"; \
    fi

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=7860
ENV STREAMLIT_PORT=7860
ENV STREAMLIT_SERVER_PORT=7860
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV ENABLE_DEMO_MODE=true
ENV ML_DEVICE=cpu

# Expose the port Hugging Face uses
EXPOSE 7860

# Health check for Hugging Face Spaces
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7860/_stcore/health || exit 1

# Run Streamlit
CMD streamlit run frontend/app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
