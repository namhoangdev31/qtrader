# Orchestrator Merge Plan (PHASE_-1_5_G2)

Establish a single "Sovereign Architectural Authority" for the QTrader system.

## 1. Target Architecture: `qtrader/core/orchestrator.py`

Final Class: `UnifiedTradingSystemOrchestrator`

### Unified Lifecycle Methods:

| Stage | Method | Logic Source |
| :--- | :--- | :--- |
| **Bootstrap** | `initialize(config: dict)` | `bot/runner.__init__`, `system/system_orchestrator.__init__` |
| **Certification** | `register_module(module)` | `system/system_orchestrator.register_module` |
| **Ingestion** | `ingest_raw_data(raw_data)` | `data/pipeline/orchestrator.process` |
| **Decision** | `compute_consensus()` | `meta/orchestrator.compute_ensemble_signal` |
| **Execution** | `run_autonomous()` | `bot/runner.start`, `core/orchestrator.run` |
| **Risk Guard** | `evaluate_fund_risk()` | `core/global_orchestrator.get_total_fund_risk` |

---

## 2. Logic Mapping Strategy

### 2.1 Extraction (Source)
Each orchestrator is treated as a logic provider:
- **`bot/runner.py`**: Principal source for HFT-optimized loops and async event handlers (`_on_market_tick`, `_on_signal`).
- **`system/system_orchestrator.py`**: Principal source for "Wiring Enforcement" and "Module Certification".
- **`data/pipeline/orchestrator.py`**: Source for "Deterministic Sequencing" of market data.

### 2.2 Unification (Target)
The logic is unified into a single class with a shared `StateStore` and `EventBus`.

---

## 3. Merge Timeline

1.  **Phase A: Hardening Core Orchestrator**
    - Expand `TradingOrchestrator` to include `register_module` and `ingest_raw_data`.
2.  **Phase B: Migrating TradingBot Logic**
    - Move `RegimeDetector` and `HFT_Optimizer` configuration to the core.
3.  **Phase C: Global Risk Integration**
    - Integrate `CapitalAllocator` and `FactorRiskEngine` calls into the coreDecision loop.
4.  **Phase D: Deletion & Entry Point Redirection**
    - Delete legacy files and update `Makefile` and `docker-compose.yaml` to point to `qtrader.core.orchestrator`.

---

## 4. Deletion Plan Summary

Candidate files for deletion:
- `qtrader/bot/runner.py`
- `qtrader/system/system_orchestrator.py`
- `qtrader/core/global_orchestrator.py`
- `qtrader/meta/orchestrator.py`
- `qtrader/data/pipeline/orchestrator.py`

> [!CAUTION]
> **No Logic Loss**: All methods listed in the `refactor_map.json` MUST be verified in the target class before deletion of source files.
