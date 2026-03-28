# QTrader System Sanitization & Integration Analysis

This document outlines the strategy for consolidating the QTrader codebase, removing redundant components, and maximizing the utility of independent infrastructure modules.

## 1. Dead Code Removal (Pruning)

Based on the System Gap Analysis and Audit Report, the following files and modules are identified as redundant, orphaned, or stagnant and are slated for removal to reduce architectural cognitive load.

### 1.1 Redundant/Duplicate Implementations

These files provide functionality that is already authoritative elsewhere in the system.

| Category | Files to Remove | Authoritative Replacement |
| :--- | :--- | :--- |
| **Kill Switch** | `risk/kill_switch.py`, `governance/kill_switch.py` | `risk/runtime.py` (+ `network_kill_switch`) |
| **Portfolio Allocator** | `portfolio/reallocator.py`, `risk/portfolio/allocator.py`, `risk/portfolio/capital_allocator.py`, `risk/portfolio_allocator_enhanced.py`, `meta/capital_allocator.py` | `portfolio/allocator.py` |
| **Accounting/NAV/Fees** | `risk/portfolio/accounting.py`, `portfolio/fee_engine.py`, `risk/portfolio/fees.py`, `portfolio/nav_engine.py` | `analytics/accounting.py`, `fee_engine.py` |
| **Orchestrator** | `core/global_orchestrator.py`, `system/system_orchestrator.py`, `meta/orchestrator.py` | `core/orchestrator.py` |
| **Execution Micro** | `execution/order_fsm.py`, `execution/reconciliation_service.py`, `execution/slippage_control.py`, `hft/microprice.py`, `hft/imbalance.py` | `oms/order_fsm.py`, `execution/reconciliation_engine.py`, `execution/slippage_model.py`, `execution/microstructure/*` |
| **ML/Regime** | `ml/regime_detector.py`, `ml/hmm_regime.py` | `ml/regime.py` |
| **Adapters** | `execution/exchange/binance_adapter.py`, `execution/adapters/binance_adapter.py` | `execution/brokers/binance.py` |

### 1.2 Orphaned Modules

Modules that are never imported and serve no active purpose.

- **Entire Packages**: `tca/`, `system/`, `governance/` (orphaned parts).
- **Meta Graveyard**: `meta/genetic.py`, `meta/memory.py`, `meta/governance_engine.py`, `meta/multi_agent.py`, `meta/self_evolution.py`, etc.
- **Audit/Compliance**: `audit/replay_audit.py`, `audit/regulatory_export.py`, `audit/compliance_exporter.py`.

---

## 2. Infrastructure Maximization (Integration Points)

Several high-grade infrastructure components exist but are underutilized or orphaned. Integrating them into the production path will immediately improve system reliability.

### 2.1 SeedManager (`core/seed_manager.py`)

- **Status**: Orphaned.
- **Max Potential**: Ensures 100% deterministic backtests and reproducible live crashes.
- **How to Use**: Call `SeedManager.apply_global()` in `TradingOrchestrator.__init__` and pass derived seeds to all ML and Alpha models.

### 2.2 FailFastEngine (`core/fail_fast_engine.py`)

- **Status**: Near-orphaned (1 importer).
- **Max Potential**: Prevents "Silent Death" by immediately halting or transitioning the system to safe-mode upon critical failures.
- **How to Use**: Integrate into the central `EventBus` error handler and `TradingOrchestrator` exception blocks.

### 2.3 DecimalAdapter (`core/decimal_adapter.py`)

- **Status**: Near-orphaned.
- **Max Potential**: Eliminates cumulative rounding errors in financial arithmetic.
- **How to Use**: Wrap all price/quantity calculations in `TradingOrchestrator` and `OMSAdapter` using `DecimalAdapter.d()`.

### 2.4 LatencyMonitor (`core/latency_monitor.py`)

- **Status**: Implemented but uninstrumented.
- **Max Potential**: Provides real-time SLA tracking for the sub-100ms pipeline budget.
- **How to Use**: Wrap `on_event` processing in `TradingOrchestrator` with latency measurements.

---

## 3. Phase-Based Implementation Plan

### Phase 1: Pruning & Consolidation (Structural Integrity)

- Delete identified redundant and orphaned files.
- Create missing `__init__.py` files to fix package structure (e.g., in `portfolio/`, `governance/`).
- Consolidate variants of Allocators and Kill Switches into the authoritative files.

### Phase 2: Core Engineering Integration (Reliability)

- Wire `SeedManager` for global determinism.
- Wire `FailFastEngine` for failure transparency.
- Enforce the use of `DecimalAdapter` in the execution and accounting path.

### Phase 3: Logic Hardening (Async & Latency)

- Remove `time.sleep` violations in `data/` and `execution/` layers.
- Implement `LatencyMonitor` instrumentation.
- Replace `copy.deepcopy` spikes with immutable state updates or windowed views.

### Phase 4: Final Validation & Compliance

- Run full TDD pipeline (Ruff, MyPy, Pytest).
- Verify audit trail coverage (Loguru integration).
- Generate final institutional readiness report.
