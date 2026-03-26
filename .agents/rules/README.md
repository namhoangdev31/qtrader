# 🛠️ KILO.AI CUSTOM RULES — INDUSTRIAL GRADE PROTOCOL

> Version: 1.0 | Project: qtrader | Updated: 2026-03-23

Mandatory rule set for all AI agents and human contributors working within this repository.

---

## Rules Index

| File                                                         | Description                                          |
| ------------------------------------------------------------ | ---------------------------------------------------- |
| [01_project_reconnaissance.md](01_project_reconnaissance.md) | Dependency check, Architecture mapping, State sync   |
| [02_atomic_coding.md](02_atomic_coding.md)                   | Single responsibility, Type hints, No hardcoding     |
| [03_tdd_pipeline.md](03_tdd_pipeline.md)                     | TDD cycle, Mocking patterns, Verification loop       |
| [04_trading_constraints.md](04_trading_constraints.md)       | No sleep, Polars memory, Log format, Look-ahead bias |
| [05_definition_of_done.md](05_definition_of_done.md)         | 10-point DoD checklist                               |
| [06_edge_cases.md](06_edge_cases.md)                         | Required edge case matrix + pattern examples         |
| [07_commands_cheatsheet.md](07_commands_cheatsheet.md)       | Dev cycle commands, DoD one-liner, shortcuts         |

---

## Quick Start — Pre-PR Verification

```bash
# Full DoD check
ruff check qtrader/ tests/ \
  && mypy qtrader/ --strict \
  && pytest tests/ --cov=qtrader --cov-fail-under=90 \
  && cd rust_core && cargo test
```

Exit code = 0 → ✅ DONE. Any errors → ❌ BLOCKED.
