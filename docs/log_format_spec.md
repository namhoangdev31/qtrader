# Logging Standard: Structured Observability (PHASE_-1_F1)

The **PHASE_-1 Logging Standard** enforces a unified, structured JSON format across all `qtrader` modules. This ensures that 100% of system actions are queryable, traceable, and audit-compliant.

## 1. Zero-Unstructured-Log Policy

- **No `print()`**: All diagnostic output must use the `qlogger.log_event()` interface.
- **No Unstructured Text**: Log files will only contain newline-delimited JSON objects.
- **Trace Accountability**: Every log entry MUST include a `trace_id` propagated from the [TraceManager](file:///Users/hoangnam/qtrader/qtrader/core/trace_manager.py).

## 2. Canonical Log Schema

Each log entry is a JSON object with the following authoritative fields:

| Field | Type | Description |
| :--- | :--- | :--- |
| `timestamp` | ISO8601 | UTC timestamp of the event. |
| `trace_id` | UUID | Lifecycle identifier linking Market data to Order fills. |
| `module` | string | Domain identifier (e.g., `execution`, `alpha`, `risk`). |
| `action` | string | The specific operation being performed. |
| `status` | Enum | Result: `SUCCESS`, `FAILURE`, `PENDING`, `RETRY`. |
| `latency_ms` | float | Time taken for the action (if applicable). |
| `metadata` | object | Contextual parameters (e.g., `order_id`, `price`). |
| `error` | string | Exception details or traceback if status is `FAILURE`. |

### Example Entry
```json
{
  "timestamp": "2026-03-28T04:01:25.123Z",
  "trace_id": "4fc2-8a12-...",
  "module": "execution",
  "action": "order_submit",
  "status": "SUCCESS",
  "latency_ms": 14.2,
  "metadata": {"symbol": "BTC", "qty": 1.5, "price": 60000}
}
```

## 3. Implementation Guard

The [QTraderLogger](file:///Users/hoangnam/qtrader/qtrader/core/logger.py) enforces this schema at runtime. It is the **Single Source of Observability Truth**.

> [!IMPORTANT]
> **Audit Compliance**: These logs are designed to meet institutional regulatory requirements (MiFID II / SEC) for trade lifecycle transparency. Any violation of this schema in production will be flagged as a critical governance breach.
