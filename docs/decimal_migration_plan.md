# Decimal Migration Roadmap: High-Precision Arithmetic

The **PHASE_-1 Numerical Audit** identified 785 high-priority floating-point violations in financial modules. This plan outlines the systematic migration of these paths to the authoritative `DecimalAdapter`.

## 1. Migration Strategy: The "Inward-Out" Approach

To minimize disruption, we migrate from the most granular accumulation points outward to high-level reporting.

| Level | Scope | Impact | Goal |
| :--- | :--- | :--- | :--- |
| **0** | Data Ingestion | HIGH | Convert price/qty decimals immediately upon receipt from API. |
| **1** | Fees & Funding | CRITICAL | Replace float math in `FeeEngine` and `FundingEngine`. |
| **2** | PnL Tracker | CRITICAL | Enforce exact arithmetic in positional PnL accumulation. |
| **3** | NAV Calculation | SYSTEMIC | Standardize global equity tracking at 12dp precision. |

---

## 2. Mandatory Refactoring Patterns

### A. Initialization Guard
**Incorrect**: `price = Decimal(10.5)`  **(Silent precision loss!)**
**Correct**: `price = d("10.5")` or `price = d(1050) / d(100)`

### B. Safe Accumulation
**Incorrect**: `self.total_fees += float_fee`
**Correct**: `self.total_fees += d(str(float_fee))`

### C. Boundary Normalization
Every module boundary (e.g., `OrderEvent`) must normalize numeric inputs using the `DecimalAdapter` factories:
- `event.price = math_authority.to_price(raw_val)`
- `event.qty = math_authority.to_qty(raw_val)`

---

## 3. Implementation Schedule

- **Sprint A**: Finalize `DecimalAdapter` and unit test coverage (COMPLETED).
- **Sprint B**: Migrate `qtrader/portfolio/fee_engine.py` and `funding_engine.py`.
- **Sprint C**: Migrate `qtrader/oms/tracker.py` and `pnl_engine.py`.
- **Sprint D**: Migrate `qtrader/core/nav_engine.py` and finalize compliance verification.

> [!IMPORTANT]
> **Production Safety Rule**: Any function marked with `# @decimal_enforced` must exclusively use `Decimal`. Mixing `float` and `Decimal` will result in a runtime `TypeError` and system halt.
