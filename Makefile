.PHONY: help install test lint check clean docker-up docker-down

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

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

rust-build:
	cd rust_core && cargo build --release
