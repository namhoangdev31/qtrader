# Trace log format & Forensic Analysis

The **PHASE_-1 Traceability System** ensures that every action is traceable across the entire system. Each trading lifecycle is assigned a unique `trace_id`.

## 1. Trace Lifecycle Chain

A single trace lifecycle progresses through these standard system points:

1.  **MARKET**: Ingestion of a row/tick into the system.
2.  **FEATURE**: Computation of technical/statistical factors.
3.  **SIGNAL**: Output from an Alpha model or Strategy.
4.  **RISK**: Post-signal risk check and allocation validation.
5.  **ORDER**: Routing of the command to the Execution Engine.
6.  **FILL**: Confirmation of trade execution from the venue.

## 2. Log Structure (Forensic)

Traces are stored in `qtrader/audit/trace_log.json` (or the `EventStore`) with the following structure:

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1718290000123,
  "module": "EXECUTION",
  "event_type": "ORDER",
  "payload": {
    "symbol": "BTC-USD",
    "side": "BUY",
    "qty": 1.0,
    "px": 65000.5
  },
  "latency_ms": 12.5
}
```

## 3. Querying Traces

To reconstruct a full lifecycle, filter the audit trail by `trace_id`:

```bash
# Example grep command for forensic investigation
cat qtrader/audit/trace_log.json | jq 'select(.trace_id == "550e8400-e29b-41d4-a716-446655440000")'
```

## 4. Latency Analysis

`latency_ms` is the time delta since the previous entry in the same `trace_id` chain.
- High latency at the **SIGNAL** stage suggests model inference bottlenecks.
- High latency at the **ORDER** stage suggests execution engine backpressure.
- High latency at the **FILL** stage suggests venue response time or network latency.
