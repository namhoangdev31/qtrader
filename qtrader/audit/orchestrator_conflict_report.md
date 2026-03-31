# Orchestrator Conflict & Fragmentation Report (PHASE_-1_5_G1)

Establish a high-fidelity map of architectural duplication and conflicts within the system control layer.

## 1. Fragmentation Score

| Metric | Value |
| :--- | :--- |
| **Total Orchestrators (|O|)** | 7 |
| **Orphaned Components** | 2 (`.clone/`) |
| **Fragmentation Score (F)** | **7.0** (High Fragmentation) |

---

## 2. Critical Conflicts

### Conflict C1: [HIGH RISK] TradingBot vs TradingOrchestrator
There consists a **90% overlap** in the execution loop responsibility between `qtrader/bot/runner.py` and `qtrader/core/orchestrator.py`.

- **Duplicated Modules**: Both initialize and manage their own instances of `ShadowEngine`, `ResourceMonitor`, and `EventBus`.
- **Race Condition Risk**: If both are instantiated, they will both attempt to subscribe to the same event streams, potentially leading to dual order execution or state store corruption.
- **Diverged Logic**: `TradingBot` includes HFT-optimized logic and regime-awareness, whereas `TradingOrchestrator` appears to be a more "canonical" but less performant version.

### Conflict C2: [MEDIUM RISK] Name Collision (SystemOrchestrator)
The class name `SystemOrchestrator` is duplicated across two fundamentally different domains:
1.  **`qtrader/system/system_orchestrator.py`**: Handles module certification and pipeline unification.
2.  **`qtrader/meta/orchestrator.py`**: Handles mathematical ensemble weighting for HFT signals.

**Risk**: Import errors and cognitive load for developers using IDE autocomplete.

---

## 3. Initialization Logic Duplication
Initialization is fragmented across the following paths:
- **Path 1**: `GlobalOrchestrator.start()` -> Registers and starts children.
- **Path 2**: `TradingBot._run_bot()` -> Dedicated bot runner.
- **Path 3**: `TradingOrchestrator.run()` -> Direct loop start.

---

## 4. Architectural Summary: FRAGMENTED
The system currently lacks a **Sovereign Authority**. Control of the trading lifecycle is distributed across competing orchestrators, which violates the **Single Source of Truth** principle of the KILO.AI Industrial Grade Protocol.

> [!CAUTION]
> **Consolidation Required**: Before proceeding with production scale-out, the system MUST unify `TradingBot` and `TradingOrchestrator` into a single, certified `UnifiedTradingOrchestrator`.
