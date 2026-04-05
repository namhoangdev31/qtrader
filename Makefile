.PHONY: help install test lint check clean up down logs log-api log-bot log-ml rust-build rust-py rust-py-dev analyst analyst-researcher analyst-trader

help:
	@echo "=== QTrader Commands ==="
	@echo ""
	@echo "  Docker:"
	@echo "    up           Build and start all services"
	@echo "    down         Stop all services"
	@echo "    logs         View all logs (follow)"
	@echo "    log-api      View dashboard API logs"
	@echo "    log-bot      View orchestrator bot logs"
	@echo "    log-ml       View ML engine logs"
	@echo ""
	@echo "  Development:"
	@echo "    install      Install local dependencies (uv sync)"
	@echo "    test         Run tests"
	@echo "    lint         Run ruff linting"
	@echo "    check        Run type checks (mypy)"
	@echo "    clean        Remove temp files"
	@echo ""
	@echo "  Rust:"
	@echo "    rust-build   Build rust core"
	@echo "    rust-py      Build Python wheel via maturin"
	@echo "    rust-py-dev  Build+install extension (dev)"
	@echo ""
	@echo "  Analyst:"
	@echo "    analyst            Launch Jupyter (all notebooks)"
	@echo "    analyst-researcher Launch Jupyter for Researcher"
	@echo "    analyst-trader     Launch Jupyter for Trader"

# --- Docker Commands ---
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

log-api:
	docker logs -f qt-dashboard

log-bot:
	docker logs -f qt-orchestrator

log-ml:
	docker logs -f qt-ml-engine

# --- Development ---
install:
	uv sync

test:
	uv run pytest tests/ -v --cov=qtrader

lint:
	uv run ruff check qtrader/ --fix

check:
	uv run mypy qtrader/ --strict

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage .mypy_cache .ruff_cache

# --- Rust ---
rust-build:
	cd rust_core && cargo build --release

rust-py:
	maturin build --release --manifest-path rust_core/Cargo.toml -i python3.10

rust-py-dev:
	maturin develop --release --manifest-path rust_core/Cargo.toml -i python3.10

# --- Analyst ---
analyst:
	uv sync --extra analyst
	uv run jupyter lab notebooks/

analyst-researcher:
	uv sync --extra analyst
	uv run jupyter lab notebooks/researcher/

analyst-trader:
	uv sync --extra analyst
	uv run jupyter lab notebooks/trader/
