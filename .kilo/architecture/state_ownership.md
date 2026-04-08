# QTRADER STATE OWNERSHIP & STATELESS STRATEGY DESIGN

> **Version:** 1.0  
> **Type:** Strict State Isolation  
> **Protocol:** KILO.AI Industrial Grade - Zero-Latency Strategy Design

---

## 1. CORE PRINCIPLE: STATELESS STRATEGY

To ensure maximum determinism, infinite horizontal scalability, and instant failover, **Strategies MUST NOT encapsulate any persistent operational state.**

- **Strategy Engine (L3)**: Functions as a pure, mathematical mapping: `(Market Data + Features) -> Signal`.
- **OMS / Execution (L5/L6)**: Manages transactional state (Orders, Fills, Positions).
- **Portfolio (L4)**: Manages financial state (Capital, NAV, Fees).

---

## 2. STATE OWNERSHIP MATRIX

| Component | Allowed State | Prohibited State |
|-----------|---------------|-------------------|
| **Strategy** | **NONE** (Pure functions) | Positions, Order Status, PnL, Capital |
| **OMS** | **Orders, Position**, Fills | Alpha Signals, Capital Allocation |
| **Portfolio** | **Capital, NAV, Fees**, Leverage | Order Book, Micro-price Models |
| **Data Feed** | Market Ticks, Snapshots | Historical PnL, Trades not yet executed |

---

## 3. INVALID STATE USAGE (RED LINES)

The following patterns represent **ARCHITECTURAL DEBT** and must trigger a `SystemHalt` during validation:

1. **Strategy storing `self.position`**: ❌  
   *Reason: Positions are owned by the `PositionManager` in OMS. If a strategy crashes, its position state is lost, causing reconciliation mismatch.*
2. **Execution storing `self.balance`**: ❌  
   *Reason: Capital and balance are owned by `PortfolioAccounting`. Execution only cares about fills.*
3. **Strategy tracking `self.pnl`**: ❌  
   *Reason: Realized/Unrealized PnL calculation is a portfolio administrative task.*

---

## 4. USAGE CONTRACT: `StateOwnershipChecker`

### Interface Specification

The `StateOwnershipChecker` is used during CI/CD and by AI coding agents to validate new code.

```python
class StateOwnershipChecker:
    """
    Enforces strict architectural boundaries on state injection.
    Used by: Static Analysis Linting / CI
    """
    
    OWNERSHIP_MAP = {
        "strategy": ["None"],
        "oms": ["order_status", "fills", "position_size", "average_price"],
        "portfolio": ["capital", "nav", "realized_pnl", "unrealized_pnl", "fees"],
        "execution": ["venue_state", "latency_metrics"]
    }

    def validate(self, module: str, variable_name: str) -> bool:
        """
        Validates if a module is allowed to 'own' or 'store' a specific state.
        Returns False if a violation is detected.
        """
        module_type = self._resolve_type(module)
        allowed = self.OWNERSHIP_MAP.get(module_type, [])
        
        if "None" in allowed and variable_name != "":
            return False
            
        return any(v in variable_name.lower() for v in allowed)

    def _resolve_type(self, module_path: str) -> str:
        # Resolves qtrader.strategy.momentum -> "strategy"
        return module_path.split(".")[1]
```

---

## 5. RECOVERY & FAILOVER DESIGN

By centralizing state in the **OMS (L6)** and **Portfolio (L4)**:
1. **Instant Strategy Restart**: If a strategy process dies, it can be restarted on any node without state synchronization. It simply receives the next `MARKET_TICK` and resumes computation.
2. **Single Source of Truth**: Position reconciliation is simplified as only one module (OMS) maintains the ground truth for open exposure.
3. **Auditability**: State transitions are logged in the `EventStore` from a single ownership point, preventing distributed state corruption.

---

## 6. TEST SPECIFICATION

### Unit: Illegal State Detection
- `test_strategy_state`: Verify that any variable like `self.current_pos` in a `BaseStrategy` subclass triggers an error.
- `test_portfolio_state`: Verify that `capital` is allowed in `AccountingEngine` but rejected in `MomentumAlpha`.

### Integration: Codebase Scan
- Run `StateOwnershipChecker` across `qtrader/` to identify existing violations (e.g., `self.last_approved_allocation` in `orchestrator.py`).

### Failure Condition
- **VIOLATION:** Any PR containing a state-ownership violation MUST NOT be merged.

---

_Documented by Antigravity — Senior Quant Engineer_
