# Uncontrolled Entry Point Audit Report (PHASE_-1_5_G3)

The QTrader system is currently operating in an **ARCHITECTURALLY FRAGMENTED** and **UNSAFE** state regarding its execution control layer.

## 1. Executive Summary

| Metric | Value | Status |
| :--- | :--- | :--- |
| Total Entry Points (|E|) | ~15 | UNSAFE |
| Controlled Entry Points | 0 | UNSAFE |
| **Control Coverage (C_entry)** | **0.0 (0.00%)** | **CAUTION** |
| Sovereign Authority | TradingOrchestrator | BYPASSED |

### Critical Findings:

- **Sovereign Violation**: Every identified entry point (API, Bot, Backtest, CLI) bypasses the centralized `TradingOrchestrator`, meaning none of them enforce the mandatory `initialize() -> validate() -> run()` sequence.
- **Broken Paths**: The `Makefile` and several integration scripts (`scripts/orchestrator_service.py`) reference deleted or non-existent orchestrators.
- **Inconsistent Initialization**: Authorities like `ConfigManager` and `TraceManager` are being manually and inconsistently initialized across scripts.

---

## 2. Uncontrolled Entry Inventory

Below is a map of the most critical uncontrolled entry points:

### 2.1 API Entry Point (`qtrader/api/api.py`)
- **Type**: FastAPI Server.
- **Current Lifecycle**: Initializes its own auth and middleware.
- **Missing Gates**: No `PipelineValidator` certification, no deterministic clock sync.
- **Severity**: HIGH (Exposes system to external queries without architectural readiness).

### 2.2 Backtest Entry Point (`qtrader/backtest/engine.py`)
- **Type**: Event-driven Simulation Runner.
- **Current Lifecycle**: Manually creates `EventBus` and data pipelines.
- **Missing Gates**: No sovereign risk management, no consolidated trace context.
- **Severity**: MEDIUM (Risk of non-deterministic backtest results vs live).

### 2.3 Bot Entry Point (`Makefile: bot-start`)
- **Type**: Live Trading Runner.
- **Current Status**: **BROKEN**. References non-existent `qtrader.bot.runner`.
- **Severity**: CRITICAL (Trading cannot be started through canonical interface).

---

## 3. Mandatory Refactoring Plan

All entry points MUST be refactored to use the `TradingOrchestrator` as their single source of truth for initialization and execution control.

### Priority 1: API Refactor
The FastAPI lifecycle should wait for `TradingOrchestrator.initialize()` and `validate()` before accepting connections.

### Priority 2: Canonical Runner
Create a sovereign runner script (e.g., `qtrader/runner.py`) that initializes the orchestrator and is called by the `Makefile`.

### Priority 3: Consolidated Service Scripts
Refactor scripts in `scripts/` to use the unified orchestrator instead of raw component initialization.
