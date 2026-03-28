# Trace Engine: End-to-End Lifecycle Tracing (PHASE_-1_F3)

The **PHASE_-1 Trace Engine** enables 100% forensic transparency for every trading event lifecycle. It ensures that every order fill can be traced back to the exact market tick that triggered it.

## 1. The Trace Chain (Institutional Lifecycle)

A valid `qtrader` lifecycle MUST encompass the following chain of stages:

1.  **`market_data:ingest`**: The arrival of a raw tick at the gateway.
2.  **`alpha:signal_gen`**: The generation of a trading signal based on the tick.
3.  **`risk:gate_check`**: Pre-trade risk validation of the signal.
4.  **`oms:order_create`**: The creation of a protocol-compliant order.
5.  **`execution:submit`**: Order submission to the exchange.
6.  **`execution:fill`**: Confirmation of order execution (Final Stage).

---

## 2. Handoff Latency: Bottleneck Detection

The **"Handoff Latency"** ($L_{handoff}$) measures the delay between stages:
$$ L_{handoff, i} = t_{start, i+1} - t_{end, i} $$

Any handoff latency exceeding **5ms** is flagged as a potential async-loop jitter or context-switch bottleneck.

## 3. Propagation Rule: Total Integrity

The system follows the **Trace Inheritance Rule**:
- **Rule**: Every downstream event created from an upstream trigger MUST inherit its `trace_id`.
- **Enforcement**: [TraceManager](file:///Users/hoangnam/qtrader/qtrader/core/trace_manager.py) enforces this via `contextvars`, making it transparent to developers.
- **Forensics**: In the event of a system failure, the `trace_id` is used to reconstruct the entire state trajectory leading up to the crash.

> [!SUCCESS]
> **Total Life Cycle Transparency**: QTrader is now "Trace-Complete". The air gap between market ticks and order fills is eliminated, ensuring 100% auditable operational flow.

---

The system is now "Lifecycle-Hardened" and ready for high-fidelity performance debugging.
