# QTRADER SYSTEM INVARIANTS

> **Version:** 1.0  
> **Type:** Institutional Guardrails  
> **Protocol:** KILO.AI High-Reliability Engineering - No Breaches Allowed

---

## 1. CORE SYSTEM INVARIANTS

These rules are non-breakable. Any violation at runtime or deployment (CI) MUST result in an immediate system error and process block via the `KillSwitch`.

| Invariant | Description | Rationale |
| --- | --- | --- |
| **No asyncio.sleep** | Prohibits the use of `asyncio.sleep` or `time.sleep` in any production event loop. | Zero latency. All timing must be deterministic and event-driven via candle/tick timestamps. |
| **Deterministic Output** | Given the same input tick sequence and initial state, the system must produce identical order flow. | Critical for research reproducibility and shadow trading verification. |
| **Recon Mismatch → Halt** | Any mismatch between OMS (internal) state and Broker (external) state must trigger an immediate halt. | Prevents runaway losses due to loss of state synchronization. |
| **Strategy Stateless** | Strategies must NOT store position, order, or capital state. All state belongs to the OMS and Portfolio layers. | Enables sub-millisecond restart and horizontally scalable alpha generation. |
| **Full Traceability** | Every order must be traceable to a specific signal, which is traceable to a specific tick and model version. | Mandatory for institutional audit and debugging. |

---

## 2. VIOLATION HANDLING

A violation of any system invariant is considered a **Category 1 Fatal Error**.

1. **Detection**: `InvariantEnforcer` detects the breach.
2. **Action**: Immediate **System Halt** or **Trading Block**.
3. **Report**: Dispatch a critical alert to the War Room with the specific invariant ID and violation context.

---

## 3. USAGE CONTRACT: `InvariantEnforcer`

The `InvariantEnforcer` runs both in high-frequency runtime loops and as a gated check in the CI/CD pipeline.

### Interface Specification

```python
class InvariantEnforcer:
    """
    Continuous validation engine for non-breakable system rules.
    Operates in CI for static rules and at runtime for dynamic states.
    """

    def check(self, system_state: dict) -> bool:
        """
        Validate all invariants for the current system state.
        
        Args:
            system_state: Current snaphot of the trading engine's state.
            
        Returns:
            True if all invariants hold, raises InvariantViolation if not.
        """
        # 1. No asyncio.sleep check (Static/Instrumented)
        # 2. Determinism check (Replay Mode)
        # 3. Recon check (OMS-to-Venue match)
        # 4. State Ownership check (Strategy introspection)
        pass
```

### Static vs. Runtime Enforcement

- **CI Enforcement**: `ruff` and custom AST checks detect `asyncio.sleep` and non-polars vectorized loops.
- **Runtime Enforcement**: `AuditEngine` detects `Recon Mismatch` or `Stateful Strategy` behavior during trade execution.

---

## 4. TEST SPECIFICATION

### Unit: Invariant Enforcement

- `test_detect_sleep`: Verify the enforcer blocks modules containing `time.sleep`.
- `test_detect_stateful_strategy`: Verify an error is raised if a strategy attempts to modify a local `position` variable.

### Integration: System-wide Check

- `test_end_to_end_invariants`: Run a full backtest simulation and verify that the `InvariantEnforcer` yields a `pass` for the entire lifecycle.

### Failure Case

- **Violation:** Any `InvariantViolation` MUST lead to a critical alert and an exit code of `1` for the process.

---

## 5. DEFINITION OF DONE (DoD)

- [x] All 5 core invariants are defined and documented.
- [x] The `InvariantEnforcer` contract is established.
- [x] No silent invariant breaches are possible.

---

###### Documented by Antigravity — Senior Quant Engineer
