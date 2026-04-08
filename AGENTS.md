# qtrader

An internal framework for trading systems and algorithms. This project operates under the **KILO.AI Industrial Grade Protocol**.

## Core Directives

1. **Never install unapproved dependencies**. The single source of truth is `pyproject.toml`.
2. **Read before you edit**. Read at least 50 lines around your target edit to match naming conventions (`snake_case` functions, `PascalCase` classes) and logic style.
3. **No magic numbers**. All parameters must be pulled from configs or function arguments.
4. **Zero Latency Rules**. `time.sleep()` or `asyncio.sleep()` are strictly forbidden in production code. Timing must be event-driven via candle timestamps.

## Code Style & Implementation

- **Polars First**: Never use pandas `df.iloc` in loops. Use Polars vectorized expressions (e.g., `pl.col().shift()`). For large datasets (>100k rows), use `.lazy()` and `.collect()`.
- **Single Responsibility**: One method solves exactly one problem.
- **Type Hints**: 100% mandatory for all public functions and methods (`mypy --strict` must pass).
- **Docstrings**: Focus on explaining parameter meanings, units (e.g., USD, ms), and constraints. Avoid writing long code examples in comments.

## Architecture & File Placement

The project structure is locked. Do not create new top-level directories or global `utils.py` files.

- **Trading Engine/Logic**: `backtest/`, `execution/`
- **Signals & Factor Models**: `alpha/` (e.g., `factor_model.py`)
- **Indicators/Factors**: `features/`
- **Risk Management**: `risk/`, `portfolio/`
- **Rules & Protocols**: `.kilo/rules/` (01 to 08)
- **Workflows**: `.kilo/workflows/` (e.g., `/factor-investing`)
- **Configs**: Stored in `configs/` root folder, managed via `core/config.py`.

## Testing (TDD Pipeline)

Every function in `qtrader/module/file.py` **must** have a corresponding test in `tests/unit/module/test_file.py`.

- **Coverage Requirement**: Maintain >90% code coverage.
- **Mocking**: Always mock external connections (`aiohttp.ClientSession` for exchanges, `asyncpg` for DB, `mlflow` for tracking) so tests run offline.
- **Look-Ahead Bias**: For every alpha/feature, write a test ensuring `compute(df_past)[i] == compute(df_full)[i]`.
- **Edge Cases to Cover**:
  - Empty DataFrames, single-row DFs, NaN/Inf values, price=0
  - Quantities=0 or negative, partial fills, position flips
  - Max drawdown exactly at limit vs exceeding limit
  - Disconnected networks, empty exchange lists.

## Logging Standards

Every trade entry/exit must be logged accurately using `loguru` in the following format:

```text
[TRADE] {timestamp} | {symbol} {side} {qty}@{price} | SL={sl} TP={tp} | Reason: {reason}
```

## Definition of Done (DoD)

Before completing any task, ensure the following commands pass successfully:

```bash
ruff check qtrader/ tests/ \
  && mypy qtrader/ --strict \
  && pytest tests/ --cov=qtrader --cov-fail-under=90 \
  && cd rust_core && cargo test
```

If exit code is 0, the task is DONE. If any errors occur, the task is BLOCKED.
