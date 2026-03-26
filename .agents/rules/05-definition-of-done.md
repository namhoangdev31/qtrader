# 5. DEFINITION OF DONE (DoD)

Before marking any module as **COMPLETED**, all check items below must be satisfied:

| # | Checklist Item | Evidence / Command |
| :--- | :--- | :--- |
| 1 | ✅ Logic correct 100% per spec | Code Review |
| 2 | ✅ Unit test coverage ≥ 90% | `pytest --cov=qtrader --cov-fail-under=90` |
| 3 | ✅ Edge cases covered | See edge cases matrix in `06_edge_cases.md` |
| 4 | ✅ All tests GREEN | `pytest tests/ -v` → exit code 0 |
| 5 | ✅ No ruff warnings/errors | `ruff check qtrader/ tests/` → exit code 0 |
| 6 | ✅ No mypy errors | `mypy qtrader/ --strict` → exit code 0 |
| 7 | ✅ Rust tests pass (if applicable) | `cd rust_core && cargo test` → all green |
| 8 | ✅ No `time.sleep()` in code | `grep -r "time.sleep" qtrader/` → empty |
| 9 | ✅ No hardcoded magic numbers | Code Review |
| 10 | ✅ Trade events log format | Audit logs with prefix `[TRADE]` |

---

## One-liner DoD Command

Run the entire verification pipeline in a single command:

```bash
ruff check qtrader/ tests/ \
  && mypy qtrader/ --strict \
  && pytest tests/ --cov=qtrader --cov-fail-under=90 \
  && cd rust_core && cargo test
```

If exit code = 0 → Module **DONE**. Any error → **BLOCKED**.
