# Financial Standard: Canonical Formulas (PHASE_-1_D4)

The **PHASE_-1 Financial Standard** establishes the authoritative mathematical definitions for all critical metrics. To ensure **ε=0 numerical consistency**, all implementations must leverage the [FinancialEngine](file:///Users/hoangnam/qtrader/qtrader/core/financial_engine.py).

## 1. Profit and Loss (PnL)

Canonical realized PnL is calculated as:
$$ PnL = (Price_{exit} - Price_{entry}) \times Quantity $$

- **Unit**: Base calculation in Asset Currency, but standardized to 18 decimal places for accumulation.
- **Constraints**: $Quantity$ must be a signed Decimal reflecting position side.

## 2. Net Asset Value (NAV)

Canonical NAV (Total Equity) is calculated as:
$$ NAV = Cash + \sum_{i \in positions} (Quantity_i \times Price_{market,i}) $$

- **Policy**: MTM (Mark-to-Market) is performed using the last known trade price or mid-price.
- **Precision**: NAV is maintained at **12 decimal places** for internal fidelity.

## 3. Transaction Fees

Fee for a given execution is calculated as:
$$ Fee = Notional \times \frac{FeeRate_{bps}}{10000} $$

- **Basis Points (bps)**: Standard unit for fee input.
- **Rounding**: Settled using `ROUND_HALF_EVEN` (Banker's Rounding) to avoid settlement bias.

## 4. Execution Slippage

### Absolute Slippage
$$ Slippage_{abs} = (Price_{exec} - Price_{ref}) \times Quantity $$
- **Directional**: Positive value = Adverse slippage (execution worse than benchmark).

### Relative Slippage (bps)
$$ Slippage_{bps} = \left| \frac{Price_{exec} - Price_{ref}}{Price_{ref}} \right| \times 10000 $$

> [!IMPORTANT]
> **Implementation Mandatory**: No module is allowed to implement these formulas in-place. All financial calculations must be called via `financial_authority` to guarantee 100% numerical consistency between Backtest and Live modes.
