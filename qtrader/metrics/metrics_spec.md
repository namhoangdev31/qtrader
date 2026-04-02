# Metrics Specification - QTrader G8

This document defines the quantitative monitoring standards for the QTrader system. Metrics are collected in real-time to track system health, performance, and risk compliance.

## Core Metrics (M)

| Metric | Type | Purpose |
| :--- | :--- | :--- |
| `latency` | Histogram (ms) | Time taken for a pipeline stage (market data -> feature -> signal). |
| `throughput` | Counter (msg/s) | Number of events processed by the orchestrator per second. |
| `error_rate` | Counter | Number of `FAILURE` statuses logged by the system. |
| `violation_rate` | Counter | Number of `VIOLATION` events triggered by the EnforcementEngine. |
| `execution_time` | Histogram (s) | Total end-to-end time for order-to-fill cycle. |

## Telemetry Pipeline

The telemetry pipeline runs as a background task within the `TradingOrchestrator`, periodically aggregating snapshots from the `MetricsRegistry` and persisting them to `qtrader/metrics/metrics_registry.json`.

## Implementation

Use the `metrics` registry from `qtrader.core.metrics`:

```python
from qtrader.core.metrics import metrics

await metrics.increment("throughput")
await metrics.observe("latency", duration_ms)
```

## Monitoring Goal

**Coverage Goal**: `C_metrics = 1.0` (100% of critical paths are monitored).
**Real-time Constraint**: Metrics aggregation MUST be async and non-blocking.
**Persistence Frequency**: Default 5 seconds.
