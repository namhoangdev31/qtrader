# ============================================================
# QTrader — Multi-Target Production Dockerfile
# ============================================================
# Optimized for: 
# 1. Image Size (Core: ~600MB, ML: ~3GB)
# 2. Build Cache Efficiency
# 3. Service-Specific Runtime
# ============================================================

# ------------------------------------------------------------
# Stage 1: SYSTEM_BUILDER — Build-time dependencies & Rust Core
# ------------------------------------------------------------
FROM python:3.10-slim AS system_builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain for compiling rust_core
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# [OPTIONAL] Pre-install maturin for wheel builds
RUN pip install --no-cache-dir maturin

# Compile Rust core → Python wheel
COPY rust_core /app/rust_core
RUN cd /app/rust_core && \
    maturin build --release -i python3.10 && \
    pip install --no-cache-dir target/wheels/*.whl

# ------------------------------------------------------------
# Stage 2: CORE_BUILDER — Lean dependencies for Orchestrator/API
# ------------------------------------------------------------
FROM system_builder AS core_builder

# Install only Core Trading Engine dependencies (FastAPI, Polars, DuckDB, etc.)
RUN pip install --no-cache-dir \
    "polars>=1.0" \
    "numpy>=2.0" \
    "scipy>=1.13" \
    "duckdb>=1.0" \
    "PyJWT>=2.8.0" \
    "mlflow>=2.14" \
    "scikit-learn>=1.5" \
    "asyncpg>=0.29" \
    "aiohttp>=3.10" \
    "uvloop>=0.20" \
    "msgpack>=1.0" \
    "pyyaml>=6.0" \
    "python-dotenv>=1.0" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.0" \
    "loguru>=0.7" \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.30" \
    "statsmodels>=0.14.6" \
    "hmmlearn>=0.3"

# ------------------------------------------------------------
# Stage 3: ML_BUILDER — Heavy dependencies for ML Engine
# ------------------------------------------------------------
FROM core_builder AS ml_builder

# Install Heavy ML Stack (Torch, Transformers, TabPFN, XGBoost)
# Using torch-cpu to save ~2.5GB of CUDA runtime bloat
RUN pip install --no-cache-dir \
    "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    "catboost>=1.2" \
    "xgboost>=2.1" \
    "lightgbm>=4.4" \
    "shap>=0.45" \
    "ray[tune]>=2.9" \
    "chronos-forecasting>=2.0" \
    tabpfn \
    transformers \
    accelerate \
    safetensors

# ------------------------------------------------------------
# Stage 4: PRODUCTION_CORE — Final image for Trading Logic (600MB)
# ------------------------------------------------------------
FROM python:3.10-slim AS production-core

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Copy Core installed Python packages
COPY --from=core_builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=core_builder /usr/local/bin /usr/local/bin

# Copy project source code (Logic only)
COPY qtrader/ /app/qtrader/
COPY live_trader.py /app/

# Ensure data directory exists for DuckDB and persistent storage
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "live_trader.py"]

# ------------------------------------------------------------
# Stage 5: PRODUCTION_ML — Final image for Intelligence Engine (3GB+)
# ------------------------------------------------------------
FROM python:3.10-slim AS production-ml

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface

# Copy ML installed Python packages
COPY --from=ml_builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=ml_builder /usr/local/bin /usr/local/bin

# Copy project source code (Logic only)
COPY qtrader/ /app/qtrader/
COPY live_trader.py /app/

# Create cache directory for models and persistent data storage
RUN mkdir -p /app/.cache/huggingface /app/data

EXPOSE 8001
CMD ["python", "-m", "qtrader.ml.atomic_trio"]
