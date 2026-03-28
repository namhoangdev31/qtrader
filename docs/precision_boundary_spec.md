# Precision Boundary Specification: Numerical Governance

The **PHASE_-1 Precision Boundary** policy defines the authoritative numerical resolution allowed for each `qtrader` domain. It establishes the "Zero Implicit Rounding" standard to ensure monetary integrity.

## 1. Boundary Contexts

Precision is enforced at the point of **domain-to-domain boundary traversal**. For example, when a high-precision intermediate (e.g., PnL 18dp) is moved to a settlement record (e.g., Cash 2dp), explicit quantization MUST be performed.

| Domain | Boundary (dp) | Rationale |
| :--- | :--- | :--- |
| `pnl_engine` | 18 | Captures ultra-fine compounding returns for institutional reporting. |
| `oms.price` | 8 | Aligns with major exchange (Binance/Coinbase) price-step standards. |
| `oms.quantity` | 6 | Aligns with major exchange quantity-step standards. |
| `risk_engine` | 12 | Precision required for margin and collateralization triggers. |
| `settlement.cash` | 2 | Final cash settlement in USD/FIAT. |

---

## 2. Propagation Rule: Signal Preservation

The system follows the **Signal Preservation Constraint**:
$$ precision_{out} = max(precision_{in}) $$

- **Internal calculations**: (e.g., raw return chains) maintain the highest required resolution without truncation.
- **Reporting layer**: (e.g., UI, CSV exports) applies the settlement boundary quantization.

## 3. Enforcement: Zero Implicit Rounding

Any value that attempts to cross a boundary without explicit `quantize()` call will trigger a `PrecisionError`.

> [!CAUTION]
> **Numerical Standard Enforcement**: If the `PrecisionValidator` detects that a value has more precision than its target domain allows, it will **Hard Fail** the system. Developers must make an intentional choice of rounding mode (e.g., `ROUND_HALF_EVEN`) to preserve auditability.

---

The system is now "Precision-Locked" to prevent hidden numerical drift.
