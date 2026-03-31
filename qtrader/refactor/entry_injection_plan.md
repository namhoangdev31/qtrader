# Sovereign Entry Point Injection Strategy (PHASE_-1_5_G3)

The goal of this phase is to ensure that every possible execution path into the QTrader system is governed by the `TradingOrchestrator` sovereign control layer.

## 1. Mandatory Sequence

Regardless of the entry type (CLI, API, Worker, Backtest), the following sequence is **MANDATORY**:

1.  **Instantiation**: Create the `TradingOrchestrator` with its required component ensemble.
2.  **`initialize()`**: Single-point activation of all Phase -1 authorities (Config, Trace, Seed, FailFast).
3.  **`validate()`**: Architectural certification check.
4.  **`run()` / `execute_pipeline()`**: Sovereign activation of the trading lifecycle.

---

## 2. Injection Patterns

### 2.1 CLI / ML Scripts
All standalone scripts MUST be wrapped in a standardized `if __name__ == "__main__":` block that uses the `SovereignRunner` template.

### 2.2 API Server
FastAPI applications MUST use the `@app.on_event("startup")` gate to ensure the orchestrator is READY before handling any HTTP traffic.

### 2.3 Backtest Engine
The `BacktestEngine` will be refactored to be a controlled component *under* the orchestrator, rather than a standalone runner.

---

## 3. Standardization Templates

Refer to [entry_wrapper_templates.py](file:///Users/hoangnam/qtrader/qtrader/refactor/entry_wrapper_templates.py) for the canonical boilerplate implementations for each entry class.
