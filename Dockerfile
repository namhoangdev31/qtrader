# ============================================================
# QTrader — Multi-Stage Dockerfile with HF ML Models
# ============================================================
# Stage 1: Base image with system dependencies
# Stage 2: Python environment with all dependencies
# Stage 3: Production image with ML models
# ============================================================

FROM python:3.10-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Disable bytecode compilation for stability
ENV UV_COMPILE_BYTECODE=0
ENV PYTHONUNBUFFERED=1
ENV HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface

# ============================================================
# Stage 2: Dependencies
# ============================================================
FROM base AS deps

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install all dependencies including ML
RUN uv sync --frozen --no-install-project

# Install HuggingFace ML packages
RUN uv pip install \
    "chronos-forecasting>=2.0" \
    tabpfn \
    transformers \
    torch \
    accelerate \
    safetensors

# ============================================================
# Stage 3: Production
# ============================================================
FROM base AS production

# Copy installed dependencies
COPY --from=deps /app/.venv /app/.venv

# Copy project code
COPY . .

# Create cache directory for HuggingFace models
RUN mkdir -p /app/.cache/huggingface

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uv", "run", "python", "live_trader.py"]

# ============================================================
# Stage 4: MLX-Optimized (Mac M4)
# ============================================================
FROM base AS mlx-production

# Copy installed dependencies
COPY --from=deps /app/.venv /app/.venv

# Install MLX packages for Mac M4
RUN uv pip install \
    mlx \
    mlx-lm \
    "chronos-forecasting>=2.0" \
    tabpfn

# Copy project code
COPY . .

# Create cache directory
RUN mkdir -p /app/.cache/huggingface

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "python", "live_trader.py"]
