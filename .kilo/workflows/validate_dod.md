---
description: Validate qtrader code against Definition of Done (DoD) requirements
---

This workflow executes the exact Definition of Done pipeline enforced by the KILO.AI Industrial Grade Protocol. You must run this workflow before marking any coding task as fully completed.

If any of the commands fail, you are BLOCKED from proceeding and must fix the errors first.

// turbo-all
1. Fix formatting with ruff: `ruff format qtrader/ tests/`
2. Lint code with ruff (auto-fix): `ruff check qtrader/ tests/ --fix`
3. Run static type checking with mypy: `mypy qtrader/ --strict`
4. Run all unit tests with full coverage requirement: `pytest tests/ --cov=qtrader --cov-fail-under=90`
5. Run rust tests for the core library: `cd rust_core && cargo test`
