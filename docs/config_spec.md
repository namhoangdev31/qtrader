# Unified Configuration Specification

The **PHASE_-1 Configuration Schema** is the single source of truth for all `qtrader` parameters. It enforces strict type-safety and value-bounding to guarantee operational integrity.

## 1. Risk Control (`risk`)

| Parameter | Type | Range | Description |
| :--- | :--- | :--- | :--- |
| `max_drawdown` | float | 0.0 - 1.0 | Absolute maximum loss percentage before system halt. |
| `max_leverage` | float | 1.0+ | Global gross exposure divided by NAV. |
| `var_limit` | float | 0.0 - 1.0 | Daily Value-at-Risk limit (95% confidence). |
| `kill_switch_enabled` | bool | T/F | If false, global kill switch will bypass child halts. |

## 2. Order Execution (`execution`)

| Parameter | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `slippage_limit_bps` | int | bps | Max allowed distance from mid-price for limit orders. |
| `latency_budget_ms` | int | ms | Soft limit for internal routing time before alerting. |
| `retry_policy` | enum | - | ["exponential", "linear", "none"]. |

## 3. Strategy Parameters (`strategy`)

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `min_signal_strength` | float | Minimum strength (0 to 1) required to emit an order. |
| `lookback_window` | int | Default bar count for rolling technical features. |
| `feature_flags` | dict | Toggle experimental HFT and risk check paths. |

## 4. Operational Guardrails (`infrastructure`)

- **`timeout_ms`**: Maximum wait time for external API calls.
- **`concurrency_limit`**: Maximum number of concurrent async tasks to prevent thread exhaustion.
- **`buffer_size`**: Internal message queue capacity for high-throughput market data.

> [!CAUTION]
> **Safe Startup Policy**: Any parameter that falls outside of its defined range will trigger an immediate **HARD FAIL** during system initialization.
