# 7. COMMANDS CHEAT SHEET

All commands required for the development lifecycle of `qtrader`.

---

## Development Cycle

```bash
# ---- 1. Format & Lint ----
ruff format qtrader/ tests/           # Auto-format (replaces black/isort)
ruff check qtrader/ tests/ --fix      # Auto-fix fixable lint issues

# ---- 2. Type Check ----
mypy qtrader/ --strict                # Zero errors required

# ---- 3. Run Tests ----
pytest tests/unit/ -v --tb=short                        # Unit tests only
pytest tests/integration/ -v --tb=short                 # Integration tests
pytest tests/ -v --tb=short                             # Run all tests

# ---- 4. Coverage ----
pytest tests/ --cov=qtrader --cov-report=term-missing   # Terminal report
pytest tests/ --cov=qtrader --cov-report=html            # HTML report → htmlcov/
pytest tests/ --cov=qtrader --cov-fail-under=90          # Fail if coverage < 90%

# ---- 5. Rust ----
cd rust_core && cargo test            # Run all Rust unit tests
cd rust_core && cargo clippy          # Rust linting
cd rust_core && cargo fmt --check     # Rust formatting check

# ---- 6. Full DoD One-liner ----
ruff check qtrader/ tests/ \
  && mypy qtrader/ --strict \
  && pytest tests/ --cov=qtrader --cov-fail-under=90 \
  && cd rust_core && cargo test
```

---

## Useful Shortcuts

```bash
# Run tests for a single module
pytest tests/unit/risk/ -v
pytest tests/unit/alpha/ -v -k "look_ahead"

# Debug a specific failing test verbosely
pytest tests/unit/execution/test_smart_order_router.py::test_best_price_buy_selects_cheapest_ask -vvs

# Check for time.sleep in production code (must yield no results)
grep -rn "time\.sleep" qtrader/

# Check for hardcoded magic numbers (manually review results)
grep -rn "[0-9]\{4,\}" qtrader/ --include="*.py" | grep -v "# "

# Rebuild rust_core (after modifying .rs sources)
cd rust_core && maturin develop
```
