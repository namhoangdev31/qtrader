# 1. PROJECT RECONNAISSANCE

> Mandatory steps before starting any code changes.

---

## 1.1 Dependency Check

**Single Source of Truth**: [`pyproject.toml`](../../pyproject.toml)

> ❌ DO NOT install any libraries not listed in the dependencies.
> ✅ If a new library is required → open a PR to update `pyproject.toml` first; do not install silently.

| Layer | Approved Libraries |
| :--- | :--- |
| Core data | `polars ≥ 1.0`, `numpy ≥ 2.0`, `duckdb ≥ 1.0` |
| ML | `scikit-learn`, `xgboost`, `catboost`, `lightgbm`, `torch`, `hmmlearn` |
| MLOps | `mlflow ≥ 2.14`, `ray[tune]` |
| Async / API | `aiohttp`, `asyncpg`, `uvloop`, `fastapi`, `uvicorn` |
| Validation | `pydantic ≥ 2.7`, `pydantic-settings` |
| Dev tools | `pytest ≥ 8.2`, `pytest-asyncio`, `pytest-cov`, `ruff ≥ 0.5`, `mypy` |

---

---

## 1.2 Architecture Mapping — Strict File Placement

The project structure is **locked**. AI agents **must not** create new top-level directories or "miscellaneous" files outside this schema.

### Core Structure (`qtrader/`)

| Directory | Purpose | Allowed File Types |
| :--- | :--- | :--- |
| `alpha/` | Signal generation logic | `*_alpha.py`, `registry.py`, `base.py` |
| `analytics/` | Performance & risk metrics | `performance.py`, `tearsheet.py`, `telemetry.py` |
| `api/` | REST/WebSocket endpoints | `router.py`, `schemas.py`, `dependencies.py` |
| `backtest/` | Simulation & historical testing | `engine.py`, `broker_sim.py`, `harness.py` |
| `bot/` | Live trading orchestration | `runner.py`, `lifecycle.py`, `state.py` |
| `core/` | Shared infra, config, logging | `event_bus.py`, `config.py`, `logger.py`, `constants.py` |
| `data/` | Market data ingestion & storage | `datalake.py`, `connectors/*.py`, `provider.py` |
| `execution/` | Order routing & execution logic | `sor.py`, `adapter.py`, `matching.py` |
| `features/` | Technical & statistical factors | `indicator.py`, `engine.py`, `store.py` |
| `feedback/` | Real-time monitoring & alerts | `monitor.py`, `subscriber.py` |
| `hft/` | Low-latency optimization | `latency_optimizer.py`, `tick_processor.py` |
| `ml/` | Model management & training | `registry.py`, `trainer.py`, `regime_detector.py` |
| `models/` | ML model wrappers | `xgboost_wrapper.py`, `torch_model.py` |
| `oms/` | Order & Position management | `order_manager.py`, `position_tracker.py` |
| `pipeline/` | End-to-end workflow management | `research.py`, `deployment.py` |
| `portfolio/` | Asset allocation & rebalancing | `optimization.py`, `allocator.py` |
| `research/` | Notebook helpers & experiments | `session.py`, `utils.py` |
| `risk/` | Pre-trade & real-time risk | `realtime.py`, `kill_switch.py`, `limits.py` |
| `strategy/` | Trading strategy implementation | `ensemble.py`, `base_strategy.py` |
| `validation/` | Data & feature validation | `validator.py`, `checks.py` |

### Test Structure (`tests/`)

| Directory | Purpose | Rule |
| :--- | :--- | :--- |
| `unit/` | Module-level tests | Must mirror `qtrader/` directory exactly. |
| `integration/` | Cross-module tests | Grouped by pipeline (e.g., `test_research_pipeline.py`) |

---

## 1.3 Strict File Creation Policy

1. **No New Folders**: Do not create any top-level directories in `qtrader/` or `tests/`.
2. **No Global Utils**: Do not create a global `utils.py` at the root. Utilities must reside within the specific module's directory (e.g., `qtrader/alpha/utils.py`).
3. **Config Files**: All YAML/JSON configs should be placed in a `configs/` folder (root) and managed via `qtrader/core/config.py`. Do not scatter `.json` files in logic folders.
4. **Authorized Only**: If a task requires a new file, it **must** fit into one of the categories above. If unsure, place it in `core/` or ask for clarification.

---

## 1.4 State Sync — Read Before You Edit

Before editing any file, **read at least 50 lines around** the edit point to:

- Match naming conventions: `snake_case` for functions/variables, `PascalCase` for classes.
- Maintain Polars expression style — no pandas, no `.iloc`.
- Respect logging patterns: `loguru` for app logs, `logging.getLogger` for library modules.
