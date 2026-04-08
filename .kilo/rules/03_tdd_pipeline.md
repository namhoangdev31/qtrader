# 3. TEST-DRIVEN DEVELOPMENT (TDD) PIPELINE

---

## 3.1 Test Creation Rules

For every `function_a` in `qtrader/module/file.py`, it is **mandatory** to create:

```text
tests/unit/module/test_file.py::test_function_a
```

Examples:

```text
qtrader/alpha/technical.py → tests/unit/alpha/test_technical_alphas.py
qtrader/risk/realtime.py   → tests/unit/risk/test_realtime_risk_engine.py
```

---

## 3.2 Mocking External Connections

Use `unittest.mock.patch` for **all** external connections to ensure tests run offline and fast:

| Connection           | Mock Target                                                                 |
| :------------------- | :-------------------------------------------------------------------------- |
| Binance/Coinbase API | `aiohttp.ClientSession`                                                     |
| MLflow               | `mlflow.search_runs`, `mlflow.set_tracking_uri`, `mlflow.pyfunc.load_model` |
| Database             | `asyncpg.Connection`, `duckdb.connect`                                      |
| File I/O             | `pytest`'s `tmp_path` fixture                                               |

```python
# ✅ Standard Pattern
@pytest.mark.asyncio
async def test_order_submission():
    with patch("qtrader.execution.binance_adapter.aiohttp.ClientSession") as m:
        m.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.json = (
            AsyncMock(return_value={"orderId": "123"})
        )
        # test body...
```

---

## 3.3 Verification Loop

```text
1. Write Test
       ↓
2. Write Implementation
       ↓
3. Run: pytest tests/unit/<module>/ -v
       ↓
   FAIL? → Return to step 2
   PASS? → Proceed to the next module
```

**Correct Commands for this Project:**

```bash
# Run unit tests
pytest tests/unit/ -v --tb=short

# Check coverage (≥ 90%)
pytest tests/unit/ --cov=qtrader --cov-report=term-missing --cov-fail-under=90

# Lint (ruff replaces flake8/black)
ruff check qtrader/ tests/
ruff format --check qtrader/ tests/

# Type check
mypy qtrader/ --strict

# Rust core tests
cd rust_core && cargo test
```
