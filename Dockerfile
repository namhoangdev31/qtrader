FROM python:3.10-slim

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

# Disable bytecode compilation for Rosetta stability
ENV UV_COMPILE_BYTECODE=0

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy project
COPY . .

# Install project
RUN uv sync --frozen

# Default command (Verification loop)
CMD ["uv", "run", "python", "scripts/verify_v4_autonomous.py"]
