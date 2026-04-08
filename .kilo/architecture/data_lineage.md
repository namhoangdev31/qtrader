# QTRADER DATA LINEAGE & TRACEABILITY

> **Version:** 1.0  
> **Type:** Full Lifecycle Traceability  
> **Protocol:** KILO.AI Audit Standard - Tier-1 Institutional Compliance

---

## 1. DATA PIPELINE FLOW

The QTrader system enforces a strict, end-to-end data lineage. Every state transition MUST be traceable back to the originating market event.

| Stage | Input | Output | Responsible Layer |
|-------|-------|--------|--------------------|
| **RAW** | WebSocket / REST | Raw JSON / Binary | L1 - Market Data |
| **NORMALIZED** | RAW | OHLCV / Tick Data | L1 - Market Data |
| **FEATURE** | NORMALIZED | Vectorized Factors | L2 - Feature/Alpha |
| **SIGNAL** | FEATURE | Entry/Exit Decision | L3 - Strategy |
| **ORDER** | SIGNAL | Execution Request | L5 - Execution |
| **FILL** | ORDER | Execution Receipt | L6 - OMS |
| **PnL** | FILL | Financial PnL Update | L4 - Portfolio |

---

## 2. LINEAGE ENFORCEMENT RULES

To maintain 100% auditability and prevent "phantom" trades:

1. **NO STEPS SKIPPED**: An `ORDER` cannot be created without a valid `SIGNAL` reference. A `SIGNAL` cannot be generated without a `FEATURE` set.
2. **GLOBAL TRACE_ID**: Every event in the pipeline MUST log a unique, monotonic `trace_id`.
3. **METADATA PERSISTENCE**: Each stage must append its own metadata (timestamp, latency, component_id) to the event trace log.

---

## 3. GLOBAL TRACE_ID STRUCTURE

A `trace_id` represents a complete lifecycle from "Market Tick" to "Position Update".

- **Originating Event**: Generated at the `NORMALIZED` stage.
- **Propagation**: Passed through every subsequent stage via the `EventBus`.
- **Termination**: Ends at the `PnL` stage when the final realized accounting update is recorded.

---

## 4. USAGE CONTRACT: `DataLineageEngine`

### Interface Specification

The `DataLineageEngine` is used for auditing, debugging, and regulatory compliance reporting.

```python
class DataLineageEngine:
    """
    Enables deep inspection of the trade lifecycle across all 7 layers.
    Used by: Audit Store / War Room Debugger / Replay Engine
    """
    
    STAGES = ["RAW", "NORMALIZED", "FEATURE", "SIGNAL", "ORDER", "FILL", "PNL"]

    def trace(self, trace_id: str) -> dict[str, any]:
        """
        Retrieves the complete audit trail for a specific trace_id.
        Returns a dictionary mapping stages to their captured data.
        """
        # Query indexed EventStore (DuckDB/Timescale)
        audit_trail = self._fetch_from_audit_store(trace_id)
        
        # Verify chain integrity
        self._verify_chain(audit_trail)
        
        return audit_trail

    def _verify_chain(self, trail: dict) -> bool:
        """
        Ensures there are no missing links.
        Alerts if a stage (e.g., FEATURE) is missing for a generated ORDER.
        """
        for i, stage in enumerate(self.STAGES):
            if stage not in trail:
                # If we have an ORDER but no SIGNAL -> ALERT!
                if i < self.STAGES.index("ORDER") and "ORDER" in trail:
                    raise LineageViolationError(f"Missing mandatory stage: {stage}")
        return True
```

---

## 5. REPLAY & DEBUGGING SCENARIOS

### Scenario 5.1: Post-Mortem Analysis
Unexpected PnL loss on `trace_id: xyz001`.
1. Call `trace("xyz001")`.
2. Inspect `FEATURE` stage: "Were factor inputs stale?"
3. Inspect `SIGNAL` stage: "Was the signal probability miscalculated?"
4. Inspect `ORDER` stage: "Was there excessive slippage in SOR?"

### Scenario 5.2: Compliance Audit
Regulatory request: "Show the origin of order id `ord_789`."
1. Lookup `trace_id` associated with `ord_789`.
2. Retrieve path back to the exact `MARKET_TICK` that triggered the factor update.

---

## 6. TEST SPECIFICATION

### Unit: Full Chain Existence
- `test_lineage_integrity`: Verify that a complete simulated lifecycle (RAW -> PnL) is correctly reconstructed.
- `test_missing_link_rejection`: Verify that the engine throws an alert if an intermediate stage (SIGNAL) is deleted from the log.

### Integration: Trade Lifecycle Simulation
- Simulate `1,000` random market events through the pipeline and verify that 100% of generated orders have 100% data lineage.

### Failure Condition
- **ALERT:** Any `trace_id` that results in an `ORDER` but has a broken lineage MUST trigger an immediate `TradingAuditAlert` to the War Room.

---

_Documented by Antigravity — Senior Quant Engineer_
