---
description: Implement a Factor Model from raw features following Quant Research standards
---

This workflow automates the transition from raw features to a standardized Factor Model using Polars.

1. **Verify Architecture**:
   - Implementation: `qtrader/alpha/factor_model.py`
   - Unit Test: `tests/unit/alpha/test_factor_model.py`

2. **Scaffold Tests First**:
   - Write tests for `FactorModel.compute()` ensuring Z-score normalization works as expected.
   - Include edge cases: Single asset, missing data, all zeros (std=0).

3. **Implement Factor Logic**:
   - Create specialized methods for **Market Factors** (Momentum, Vol, Trend).
   - Create specialized methods for **Style Factors** (Mean Reversion, Breakout).
   - Use `pl.struct()` or `JOIN` to handle multi-symbol cross-sectional mapping.

4. **Standardize & Aggregate**:
   - Implement `_standardize(df: pl.DataFrame, col: str) -> pl.Series`.
   - Compute `composite_alpha` as a weighted combination of Z-scores.

5. **Verify DoD**:
   // turbo
6. Run unit tests: `pytest tests/unit/alpha/test_factor_model.py`
   // turbo
7. Verify type hints: `mypy qtrader/alpha/factor_model.py --strict`
   // turbo
8. Run full DoD check: `ruff check qtrader/alpha/factor_model.py`
