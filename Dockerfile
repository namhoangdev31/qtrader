FROM python:3.12-slim

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

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Install dependencies
COPY pyproject.toml .
RUN uv sync --frozen --no-install-project

# Copy project
COPY . .

# Install project
RUN uv sync --frozen

# Default command
CMD ["python", "-m", "qtrader.scripts.backtest"]
