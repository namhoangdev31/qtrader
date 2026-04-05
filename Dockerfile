# ============================================================
# QTrader — Production Dockerfile (pip + system Python)
# ============================================================
# Strategy: Install everything into system Python (no venv).
# This avoids all .venv path issues and exec format errors.
# ============================================================

# ------------------------------------------------------------
# Stage 1: BUILDER — Install deps + compile Rust
# ------------------------------------------------------------
FROM python:3.10-slim AS builder

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

# Install Python dependencies via pip (system-wide, no venv)
RUN pip install --no-cache-dir \
    "polars>=1.0" \
    "numpy>=2.0" \
    "scipy>=1.13" \
    "duckdb>=1.0" \
    "PyJWT>=2.8.0" \
    "catboost>=1.2" \
    "xgboost>=2.1" \
    "lightgbm>=4.4" \
    "shap>=0.45" \
    "mlflow>=2.14" \
    "scikit-learn>=1.5" \
    "ray[tune]>=2.9" \
    "torch>=2.2" \
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

# Install ML extras
RUN pip install --no-cache-dir \
    "chronos-forecasting>=2.0" \
    tabpfn \
    transformers \
    accelerate \
    safetensors

# Compile Rust core → Python wheel
COPY rust_core /app/rust_core
RUN pip install --no-cache-dir maturin && \
    cd /app/rust_core && \
    maturin build --release -i python3.10 && \
    pip install --no-cache-dir target/wheels/*.whl

# ------------------------------------------------------------
# Stage 2: PRODUCTION — Lean runtime image
# ------------------------------------------------------------
FROM python:3.10-slim AS production

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface

# Copy installed Python packages from builder (system-wide)
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project source code (baked into image, not bind-mounted)
COPY qtrader/ /app/qtrader/
COPY rust_core/ /app/rust_core/
COPY live_trader.py /app/

# Create cache directory for HuggingFace models
RUN mkdir -p /app/.cache/huggingface

EXPOSE 8000

# Default command (overridden by docker-compose per service)
CMD ["python", "live_trader.py"]
