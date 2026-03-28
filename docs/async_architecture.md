# Async Architecture: Non-Blocking Execution Pipeline (PHASE_-1_E2)

The **PHASE_-1 Async Architecture** transforms the `qtrader` platform into a high-performance, event-driven execution engine. It enforces a strict "Zero-Sync" policy to guarantee sub-100ms end-to-end latency.

## 1. The Execution Path (CriticalPath)

The execution lifecycle must be 100% non-blocking. 

### Ingestion → Signal → Order Lifecycle:
1.  **Market Data Ingestion**: `asyncio-based` connector (Binance/Coinbase) ingests ticks.
2.  **Alpha Generation**: Processed via Polars (vectorized) in non-blocking tasks.
3.  **Risk Pre-Gate**: Asynchronous validation of VaR and limits.
4.  **Order Routing**: Sub-ms order submission using shared `aiohttp` sessions via `AsyncAdapter`.

---

## 2. Core Authorities: Async Core

| Module | Authority | Purpose |
| :--- | :--- | :--- |
| **Async Management** | [AsyncAdapter](file:///Users/hoangnam/qtrader/qtrader/core/async_adapter.py) | Centralizes shared `ClientSession` and background task management. |
| **Concurrency Guard**| [ConcurrencyGuard](file:///Users/hoangnam/qtrader/qtrader/core/concurrency_guard.py) | (Planned) Enforces atomic async locks for shared portfolio state. |
| **Latency Monitor** | [LatencyMonitor](file:///Users/hoangnam/qtrader/qtrader/core/latency_monitor.py) | (Planned) Instruments every stage of the transit path. |

---

## 3. The Zero-Sync Mandate

The system enforces a **Zero-Sync-Lock** policy. Any operation that blocks the event loop is a **CRITICAL GOVERNANCE BREACH**.

### Forbidden Primitives:
- **`time.sleep()`**: Triggers a Fail-Fast system halt.
- **`requests.*`**: Must be replaced with `aiohttp` via `async_authority.get_session()`.
- **`sys.open()`**: Critical file operations must use `aiofiles` or be offloaded via `run_in_executor`.
- **`deepcopy()`**: Must be avoided in the hot execution path (prefer immutable event models).

### Thread Offloading:
Utility tasks (logging to disk, reporting) that cannot be async-native must be wrapped in `asyncio.run_in_executor` to prevent latency jitter on the main loop.

```python
# Standard Pattern
async def process_market_event(event):
    # 100% async path
    signal = await alpha_engine.generate(event)
    if signal:
        task = spawn_task(execution_engine.execute(signal))
```

The system is now "Async-First" to ensure total performance integrity.
