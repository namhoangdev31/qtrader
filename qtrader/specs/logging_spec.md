# Logging Specification - QTrader G8

This document defines the structured logging standards for the QTrader trading system. All execution points must emit JSON-serializable logs to ensure 100% queryable and audit-compliant traces.

## Standard Log Schema (JSON)

Every log entry MUST contain the following fields:

| Field | Type | Description |
| :--- | :--- | :--- |
| `timestamp` | `string` | ISO 8601 with Zulu time (e.g., `2026-04-01T12:00:00Z`). |
| `trace_id` | `string` | The UUID of the current execution trace. MUST be `NO_TRACE` if not available. |
| `module` | `string` | The functional module (e.g., `orchestrator`, `alpha`, `risk`, `oms`). |
| `action` | `string` | The specific system action (e.g., `MARKET_DATA_RECEIVED`, `ORDER_ROUTED`). |
| `status` | `string` | Result status: `SUCCESS`, `FAILURE`, or `WARNING`. |
| `level` | `string` | Loguru standard levels: `INFO`, `DEBUG`, `ERROR`, `SUCCESS`, `CRITICAL`. |
| `message` | `string` | Human-readable context. |
| `latency_ms` | `float` | (Optional) Performance measurement for the action. |
| `metadata` | `object` | (Optional) Additional context (e.g., `symbol`, `quantity`, `price`). |
| `error` | `string` | (Optional) Error traceback or message on `FAILURE`. |

## Core Implementation

Use the `log_event` function from `qtrader.core.logger`:

```python
from qtrader.core.logger import log_event

log_event(
    module="orchestrator",
    action="MARKET_DATA_RECEIVED",
    status="SUCCESS",
    metadata={"symbol": "BTC/USDT", "price": 65000.5}
)
```

## Mandatory Injection Points

1. **Pre-Execution**: `System readiness checks`, `validation results`.
2. **Handle Market Data**: Arrival of raw data, completion of normalization.
3. **Alpha Generation**: Start and end of each alpha module's computation.
4. **Feature Validation**: Result of feature compliance checks.
5. **Signal Ensemble**: Combined signal output.
6. **Risk Management**: Pre-trade risk check results.
7. **Order Execution**: Order submission to OMS, fill updates.
8. **Post-Execution**: Shutdown status, final audit report results.

## Observability Goal

**Coverage Goal**: `C_log = 1.0` (100% of pipeline events are logged).
**Zero Latency Rule**: Logging must be non-blocking. `loguru`'s default behavior is acceptable for this phase.
