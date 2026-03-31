.PHONY: help install test lint check clean docker-up docker-down rust-build rust-py rust-py-dev analyst analyst-researcher analyst-trader bot-start bot-stop

help:
	@echo "Available commands:"
	@echo "  install     Install dependencies"
	@echo "  test        Run tests"
	@echo "  lint        Run ruff linting"
	@echo "  check       Run type checks (mypy)"
	@echo "  clean       Remove temporary files"
	@echo "  docker-up   Start docker services"
	@echo "  docker-down Stop docker services"
	@echo "  rust-build  Build rust core"
	@echo "  rust-py     Build Python wheel via maturin"
	@echo "  rust-py-dev Build+install extension (dev)"
	@echo "  analyst             Install analyst deps + launch Jupyter (all notebooks)"
	@echo "  analyst-researcher  Launch Jupyter for Researcher notebooks"
	@echo "  analyst-trader      Launch Jupyter for Trader notebooks"
	@echo "  bot-start   Start trading bot (paper config)"
	@echo "  bot-stop    Stop trading bot"

install:
	uv sync

active:
	source .venv/bin/activate

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

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

rust-build:
	cd rust_core && cargo build --release

rust-py:
	maturin build --release --manifest-path rust_core/Cargo.toml -i python3.10

rust-py-dev:
	maturin develop --release --manifest-path rust_core/Cargo.toml -i python3.10

analyst:
	uv sync --extra analyst
	uv run jupyter lab notebooks/

analyst-researcher:
	uv sync --extra analyst
	uv run jupyter lab notebooks/researcher/

analyst-trader:
	uv sync --extra analyst
	uv run jupyter lab notebooks/trader/

bot-start:
	uv run python -m qtrader.runner configs/bot_paper.yaml

bot-stop:
	@echo "Send SIGINT (Ctrl+C) to the bot process to stop."
