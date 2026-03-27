# QTRADER — SYSTEM GAP ANALYSIS v5.0

> **Audit Date**: 2026-03-27
> **Benchmark**: [standash-document.md](standash-document.md) (Tier-1 Institutional Master Specification)
> **Scope**: Final Architectural Reckoning (404 Python files)
> **Methodology**: Static integrity, numeric precision, concurrency safety, memory/leak analysis, performance de-vectorization check

---

## EXECUTIVE SUMMARY

|  Metric  |  Value  |  Assessment  |
|:---|:---|:---|
|  Total Python files  |  **404**  |  Sprawling  |
|  Non-init modules  |  **362**  |  Over-engineered  |
|  Test files  |  **210**  |  58% coverage ratio  |
| **Integrated Core Flow** | **~55%** | 🔴 CRITICAL GAP |
| **Concurrency Safety** | **None** | 🔴 2 locks in 404 files |
| **De-vectorization** | **Risky** | 🔴 .to_list() in core path |
| **Latency Jitter** | **High** | 🔴 111 execution loggers |
| **Numeric Precision** | **Risky** | 🔴 229 float instances |
| **Deterministic Entropy** | **Failing** | 🔴 52 unseeded randoms |
| **Security Handling** | **Unsigned** | 🔴 106 unsigned calls |
| **Memory Governance** | **At-Risk** | 🔴 Unbounded lists found |
| **Error Handling** | **Unsafe** | 🔴 32 silent exceptions |
| **Hardcoding Discipline** | **Magic** | 🔴 Hardcoded strategy weights |
| **Stateful Resilience** | **Zero** | 🔴 No state sync/failover |
| **Market Safety**| **None** | 🔴 No War Mode (Preservation) |
| **Orphaned modules** | **~80** | 🔴 CRITICAL |
| **Duplicate clusters** | **18** | 🔴 CRITICAL |
| **Missing init files** | **11** | 🔴 CRITICAL |
|  **PTP/Clock Drift Control** (<1ms alert)  |  **Lacking**  |  🟡 WARNING  |
|  **ML Explainability** (SHAP/LIME)  |  **Missing**  |  🟡 WARNING  |
|  Stub methods (return `[]`/`{}`/`None`)  |  **~60**  |  🟡 WARNING  |
|  **HFT CPU Pinning** (missing cores pinning)  |  **Missing**  |  🟡 WARNING  |

### Overall Production Readiness: 🔴 NOT READY

The system has extensive breadth but suffers from **architectural fragmentation**: massive module duplication, ~80 orphaned files never connected to any import chain, and dozens of stub methods returning hardcoded empty values. The codebase resembles a collection of independently developed prototypes rather than an integrated institutional platform.

---

## 1. ARCHITECTURAL FRAGMENTATION — CRITICAL DUPLICATES

The most severe structural deficiency. **18 functional domains** have duplicate implementations scattered across multiple modules, violating the Single Responsibility principle and creating confusion about which is the "canonical" version.

### 1.1 Kill Switch (3 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `risk/kill_switch.py`  |  risk/  |  ✅ Active (GlobalKillSwitch)  |
|  `governance/kill_switch.py`  |  governance/  |  🔴 Orphan — never imported  |
|  `risk/network_kill_switch.py`  |  risk/  |  ⚠️ Unclear relationship  |

**Impact**: In a production kill switch scenario, it is ambiguous which module is authoritative. This is **life-or-death for capital protection**.

### 1.2 Portfolio Allocator (6 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `portfolio/allocator.py`  |  portfolio/  |  ⚠️ Unclear canonical  |
|  `portfolio/reallocator.py`  |  portfolio/  |  🔴 Orphan  |
|  `risk/portfolio/allocator.py`  |  risk/portfolio/  |  ⚠️ Active but fragmented  |
|  `risk/portfolio/capital_allocator.py`  |  risk/portfolio/  |  ⚠️ Active but fragmented  |
|  `risk/portfolio_allocator_enhanced.py`  |  risk/  |  ⚠️ 454 lines, active  |
|  `meta/capital_allocator.py`  |  meta/  |  🔴 Orphan  |

**Impact**: Capital allocation logic is the **central nervous system** of fund management. 6 overlapping implementations create risk of inconsistent position sizing.

### 1.3 Accounting / NAV / Fees (6 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `analytics/accounting.py`  |  analytics/  |  ✅ Active  |
|  `risk/portfolio/accounting.py`  |  risk/portfolio/  |  ⚠️ Duplicate  |
|  `analytics/fee_engine.py`  |  analytics/  |  ✅ Active  |
|  `portfolio/fee_engine.py`  |  portfolio/  |  🔴 Orphan  |
|  `risk/portfolio/fees.py`  |  risk/portfolio/  |  ⚠️ Duplicate  |
|  `portfolio/nav_engine.py`  |  portfolio/  |  🔴 Orphan  |

**Impact**: Dual accounting engines can produce different NAV/PnL values — a regulatory and financial integrity disaster.

### 1.4 Orchestrator (5 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `core/orchestrator.py`  |  core/  |  ✅ Active (726 lines)  |
|  `core/global_orchestrator.py`  |  core/  |  ⚠️ Partial overlap  |
|  `meta/orchestrator.py`  |  meta/  |  🔴 Orphan  |
|  `system/system_orchestrator.py`  |  system/  |  🔴 Orphan  |
|  `data/pipeline/orchestrator.py`  |  data/pipeline/  |  ✅ Active (data-specific)  |

**Impact**: Multiple orchestrators compete for "system brain" status. Only `core/orchestrator.py` appears genuinely integrated.

### 1.5 Order FSM (2 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `oms/order_fsm.py`  |  oms/  |  ✅ Active  |
|  `execution/order_fsm.py`  |  execution/  |  🔴 Orphan  |

**Impact**: Standash §7.1 mandates a single authoritative FSM. Two implementations risk state divergence.

### 1.6 Reconciliation (2 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/reconciliation_engine.py`  |  execution/  |  ✅ Active  |
|  `execution/reconciliation_service.py`  |  execution/  |  🔴 Orphan  |

### 1.7 Slippage (3 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/slippage_model.py`  |  execution/  |  ✅ Active  |
|  `execution/slippage_control.py`  |  execution/  |  🔴 Orphan  |
|  `tca/slippage.py`  |  tca/  |  🔴 Orphan  |

### 1.8 Microprice (2 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/microstructure/microprice.py`  |  execution/  |  ⚠️ Active  |
|  `hft/microprice.py`  |  hft/  |  🔴 Orphan  |

### 1.9 Imbalance (2 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/microstructure/imbalance.py`  |  execution/  |  ⚠️ Active  |
|  `hft/imbalance.py`  |  hft/  |  🔴 Orphan  |

### 1.10 RL Agent (3 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/rl/agent.py`  |  execution/rl/  |  ✅ Active  |
|  `execution/rl_agent.py`  |  execution/  |  🔴 Orphan  |
|  `hft/rl_agent.py`  |  hft/  |  🔴 Orphan  |

### 1.11 Cost Model (2 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/cost_model.py`  |  execution/  |  ✅ Active  |
|  `execution/routing/cost_model.py`  |  execution/routing/  |  🔴 Orphan  |

### 1.12 Position Sizing (3 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `portfolio/position_sizing.py`  |  portfolio/  |  🔴 Orphan  |
|  `risk/portfolio/position_sizing.py`  |  risk/portfolio/  |  ⚠️ Minimal (34 lines)  |
|  `risk/portfolio/sizing.py`  |  risk/portfolio/  |  ⚠️ Alternative  |
|  `risk/position_sizer.py`  |  risk/  |  ⚠️ Yet another  |

### 1.13 Regime Detection (3+ implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `ml/regime.py`  |  ml/  |  ✅ Active (337 lines)  |
|  `ml/regime_detector.py`  |  ml/  |  🔴 Orphan (463 lines)  |
|  `ml/hmm_regime.py`  |  ml/  |  🔴 Orphan  |

### 1.14 TCA (5 implementations across 2 modules)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `tca/` (6 files)  |  tca/  |  🔴 Entire module orphaned  |
|  `analytics/tca_engine.py`  |  analytics/  |  ✅ Active  |
|  `analytics/tca_models.py`  |  analytics/  |  ✅ Active  |

### 1.15 Binance Adapter (3 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/brokers/binance.py`  |  execution/brokers/  |  ✅ Active  |
|  `execution/exchange/binance_adapter.py`  |  execution/exchange/  |  🔴 Orphan  |
|  `execution/adapters/binance_adapter.py`  |  execution/adapters/  |  🔴 Orphan  |

### 1.16 Orderbook (4 implementations)

|  File  |  Location  |  Status  |
|:---|:---|:---|
|  `execution/orderbook_core.py`  |  execution/  |  ⚠️ Minimal (22 lines)  |
|  `execution/orderbook_enhanced.py`  |  execution/  |  ✅ Active (437 lines)  |
|  `execution/orderbook_simulator.py`  |  execution/  |  ⚠️ Active  |
|  `execution/benchmark_orderbook.py`  |  execution/  |  🔴 Orphan  |

---

## 2. ORPHANED MODULES — FULL INVENTORY

The following **80 files** are never imported by any other module in the codebase. They exist but serve no purpose in the running system.

### 2.1 Entirely Orphaned Packages

|  Package  |  Files  |  Assessment  |
|:---|:---|:---|
|  `tca/` (6 files)  |  venue_ranking, cost_attribution, implementation_shortfall, tca_report, slippage, benchmark  |  🔴 Entire module disconnected. Duplicated by `analytics/tca_*`  |
|  `feedback/` (2 files)  |  incident_handler, dashboard  |  🔴 Entire module disconnected. Recently created but never wired  |
|  `system/` (2 files)  |  system_orchestrator, pipeline_validator  |  🔴 Entire module disconnected  |
|  `governance/` (partial)  |  model_risk, approval_pipeline  |  🔴 Orphaned despite having tests  |

### 2.2 Orphaned by Module

#### `meta/` — 13 of 15 files orphaned

|  File  |  Lines  |  Assessment  |
|:---|:---|:---|
|  genetic.py  |  —  |  🔴 Never imported  |
|  self_diagnostic.py  |  —  |  🔴 Never imported  |
|  memory.py  |  —  |  🔴 Never imported  |
|  governance_engine.py  |  —  |  🔴 Never imported  |
|  risk_filter.py  |  —  |  🔴 Never imported  |
|  deployment_pipeline.py  |  —  |  🔴 Never imported  |
|  multi_agent.py  |  —  |  🔴 Never imported  |
|  lifecycle_manager.py  |  —  |  🔴 Never imported  |
|  audit_logger.py  |  —  |  🔴 Never imported  |
|  research_loop.py  |  —  |  🔴 Never imported  |
|  approval_system.py  |  —  |  🔴 Never imported  |
|  shadow_enforcer.py  |  —  |  🔴 Never imported  |
|  self_evolution.py  |  —  |  🔴 Never imported  |
|  constraint_engine.py  |  —  |  🔴 Never imported  |

**Verdict**: The `meta/` module is a graveyard of aspirational code. 87% of its files serve no purpose.

#### `execution/` — 15+ files orphaned

|  File  |  Assessment  |
|:---|:---|
|  benchmark_orderbook.py  |  🔴 Orphan  |
|  adverse_model.py  |  🔴 Orphan  |
|  execution_monitor.py  |  🔴 Orphan  |
|  microstructure/queue_model.py  |  🔴 Orphan  |
|  microstructure/toxic_flow.py  |  🔴 Orphan  |
|  microstructure/spread_model.py  |  🔴 Orphan  |
|  microstructure/hidden_liquidity.py  |  🔴 Orphan  |
|  exchange/binance_adapter.py  |  🔴 Duplicate orphan  |
|  exchange/coinbase_adapter.py  |  🔴 Duplicate orphan  |
|  reconciliation_service.py  |  🔴 Duplicate orphan  |
|  degradation_handler.py  |  🔴 Orphan  |
|  order_id.py  |  🔴 Orphan  |
|  state_builder.py  |  🔴 Orphan  |
|  adapters/binance_adapter.py  |  🔴 Duplicate orphan  |
|  adapters/broker_bridge.py  |  🔴 Orphan  |
|  retry_handler.py  |  🔴 Orphan (contains sleep violation)  |
|  rl_agent.py  |  🔴 Duplicate orphan  |
|  rl/reward.py  |  🔴 Orphan  |
|  execution_quality.py  |  🔴 Orphan  |
|  strategy/slicing.py  |  🔴 Orphan  |
|  strategy/scheduler.py  |  🔴 Orphan  |
|  slippage_control.py  |  🔴 Orphan  |

#### `hft/` — 5 of 8 files orphaned

|  File  |  Assessment  |
|:---|:---|
|  queue_model.py  |  🔴 Duplicate of execution/microstructure/  |
|  spoofing.py  |  🔴 Orphan  |
|  toxic_flow.py  |  🔴 Duplicate orphan  |
|  market_maker.py  |  🔴 Orphan  |
|  rl_agent.py  |  🔴 Duplicate orphan  |

#### `portfolio/` — 7+ files orphaned

|  File  |  Assessment  |
|:---|:---|
|  risk_monitor.py  |  🔴 Orphan  |
|  funding_engine.py  |  🔴 Orphan  |
|  scaling_governor.py  |  🔴 Orphan  |
|  position_sizing.py  |  🔴 Orphan (duplicate)  |
|  cash_ledger.py  |  🔴 Orphan  |
|  nav_engine.py  |  🔴 Orphan  |
|  capital_flow.py  |  🔴 Orphan  |
|  drawdown_controller.py  |  🔴 Orphan  |

#### `backtest/` — 4 files orphaned

|  File  |  Assessment  |
|:---|:---|
|  l2_broker_sim.py  |  🔴 Orphan  |
|  walk_forward_bt.py  |  🔴 Orphan  |
|  tick_engine.py  |  🔴 Orphan  |
|  multi_asset.py  |  🔴 Orphan  |

#### Other Orphans

|  File  |  Assessment  |
|:---|:---|
|  `ml/regime_detector.py`  |  🔴 Orphan (463 lines wasted)  |
|  `ml/model_comparator.py`  |  🔴 Orphan  |
|  `ml/hmm_regime.py`  |  🔴 Orphan  |
|  `models/catboost_model.py`  |  🔴 Orphan  |
|  `audit/replay_audit.py`  |  🔴 Orphan  |
|  `audit/regulatory_export.py`  |  🔴 Orphan  |
|  `audit/dashboard.py`  |  🔴 Orphan  |
|  `audit/trade_audit.py`  |  🔴 Orphan  |
|  `audit/compliance_exporter.py`  |  🔴 Orphan  |
|  `research/walkforward.py`  |  🔴 Orphan  |
|  `oms/interface.py`  |  🔴 Orphan  |
|  `oms/replay_engine.py`  |  🔴 Orphan  |
|  `oms/oms_multi_adapter.py`  |  🔴 Orphan  |
|  `pipeline/deployment.py`  |  🔴 Orphan  |
|  `pipeline/session_bridge.py`  |  🔴 Orphan  |
|  `core/event_validator.py`  |  🔴 Orphan  |
|  `core/event_bus_adapter.py`  |  🔴 Orphan  |
|  `features/technical/indicators.py`  |  🔴 Orphan  |

---

## 3. MISSING `__init__.py` — BROKEN PACKAGE STRUCTURE

The following directories contain Python modules but lack `__init__.py`, meaning they **cannot be imported as packages**:

|  Directory  |  File Count  |  Impact  |
|:---|:---|:---|
|  `qtrader/tca/`  |  6  |  🔴 Entire TCA module unimportable  |
|  `qtrader/feedback/`  |  2  |  🔴 Incident handler / dashboard unimportable  |
|  `qtrader/system/`  |  2  |  🔴 System orchestrator unimportable  |
|  `qtrader/governance/`  |  6  |  🔴 All governance modules unimportable  |
|  `qtrader/portfolio/`  |  14  |  🔴 All portfolio modules unimportable  |
|  `qtrader/certification/`  |  13  |  🔴 All certification modules unimportable  |
|  `qtrader/execution/microstructure/`  |  6  |  🔴 Microstructure analysis unimportable  |
|  `qtrader/execution/core/`  |  1  |  🔴 Fill probability unimportable  |
|  `qtrader/execution/routing/`  |  4  |  🔴 Smart routing unimportable  |
|  `qtrader/execution/rl/`  |  4  |  🔴 RL execution unimportable  |
|  `qtrader/execution/strategy/`  |  2  |  🔴 Execution strategy unimportable  |

**Total**: 11 directories with 60+ files that **cannot function as Python packages**.

---

## 4. ZERO LATENCY VIOLATIONS

Standash §2.5 and AGENTS.md strictly forbid `time.sleep()` / `asyncio.sleep()` in production code.

|  File  |  Violation  |  Severity  |
|:---|:---|:---|
|  `core/timer.py:63,70`  |  `await asyncio.sleep(self.interval_s)`  |  🟡 Timer utility — may be acceptable  |
|  `execution/retry_handler.py:36`  |  `await asyncio.sleep(delay)`  |  🔴 Production violation  |
|  `execution/reconciliation_engine.py:44`  |  `await asyncio.sleep(0.1)`  |  🔴 Production violation  |
|  `data/market/coinbase_market.py:136,140`  |  `time.sleep(0.15)`, `time.sleep(1.0)`  |  🔴 Blocking sleep in data layer  |
|  `data/market/snapshot_recovery.py:99`  |  `await asyncio.sleep(0.02)`  |  🟡 Simulated latency  |
|  `data/market/clock_sync.py:113,118`  |  `await asyncio.sleep(...)`  |  🟡 Clock sync loop  |

---

## 5. DEEP LOGIC AUDIT — STANDASH PHILOSOPHY CHECK

Beyond file structure, we audited the codebase against the **Core Principles** defined in Standash §2.

### 5.1 Determinism First (§2.1) — 🔴 FAILED

*   **Finding**: **52 instances** of unseeded randomness (`random.random()`, `random.choice()`, `np.random.normal()`) found in critical paths.
*   **High Risk Area**: `meta/genetic.py` and `meta/strategy_generator.py` use bare randomness for alpha generation. Two Sigma/Renaissance standards require fixed seeds for all research to ensure reproducibility.
*   **Impact**: Backtests may not be reproducible; production signals could diverge from research due to uncontrolled entropy.

### 5.2 Stateless Strategy Design (§2.5) — ✅ PASSED

*   **Finding**: Zero (0) instances of strategies holding local `self.positions` or `self.balance` in `qtrader/strategy/`.
*   **Impact**: Excellent adherence to Tier-1 standards. Strategies correctly depend on external state feeds, ensuring crash-recovery resilience.

### 5.3 Security Hardening (§5.3 / §263) — 🔴 FAILED

*   **Finding**: Zero (0) instances of `sign_order` or `sign_request` in the `execution/` layer.
*   **Impact**: Although a `security/` module exists, it is not wired into the order submission flow. Orders are sent without cryptographic signatures or institutional-grade verification.

### 5.4 CPU Pinning & HFT Isolation (§4.10) — 🟡 PARTIAL

*   **Finding**: `psutil` is used for resource monitoring, but there is no logic for **Core Pinning** or **CPU Isolation** for the core execution/alpha threads.
*   **Impact**: System performance is subject to OS scheduling jitter (>10ms), violating the <1ms drift requirement.

### 5.5 Stateful Replication & Failover (§252-253) — 🔴 FAILED

*   **Finding**: Zero (0) instances of `replication` or `state_sync` logic found for OMS/Redundancy.
*   **Impact**: The system cannot achieve the "< 5 seconds failover" target as there is no mechanism to sync order state between backup nodes.

### 5.6 Capital Preservation Mode (War Mode) (§272-274) — 🔴 FAILED

*   **Finding**: Logic for `war_mode` or `capital_preservation` is completely missing from the `risk/` and `strategy/` layers.
*   **Impact**: In extreme market conditions, the system cannot autonomously transition to a "Reduced Exposure / Hedging-only" state.

### 5.7 Institutional Audit of Overrides (§309) — 🔴 FAILED

*   **Finding**: Zero (0) evidence that manual overrides from `security/override_system.py` are logged into the central `audit/audit_store.py`.
*   **Impact**: Lack of non-repudiation for human interventions.

### 5.8 Explainability & Factor Attribution (§13) — 🔴 FAILED
*   **Finding**: No evidence of SHAP, LIME, or factor-based attribution in the `ml/` or `analytics/` layers.
*   **Impact**: Violates "Institutional Transparency" (Explainability) standards.

---

## 6. ULTRA-DEEP CODE DISCIPLINE AUDIT

### 6.1 Numeric Precision Audit (§2.1 / §4.1) — 🔴 FAILED
*   **Finding**: **229 instances** of `float` usage in precision-sensitive financial logic (`oms/`, `portfolio/`, `analytics/`).
*   **Evidence**:
    - `oms/interface.py:50,60`: `get_cash()` and `get_positions()` return `float`.
    - `oms/event_store.py:77,99`: Explicitly casting prices with `float(price)`.
*   **Impact**: Cumulative rounding errors in PnL, position sizing, and NAV. Institutional systems require `Decimal`.

### 6.2 Memory Governance Audit (§5.1) — 🔴 FAILED
*   **Finding**: Core components use unbounded lists without windowing or persistence-cleanup mechanics.
*   **Evidence**:
    - `core/state_store.py:134`: `self._state.equity_curve.append(...)` grows indefinitely.
    - `core/event_bus.py:70`: `self._worker_tasks.append(task)` never removes tasks.
*   **Impact**: Production processes will eventually crash due to Out-of-Memory (OOM) after weeks/months of uptime.

### 6.3 Silent Failure Patterns (§2.2) — 🔴 FAILED
*   **Finding**: **32 instances** of non-specific `except Exception:` blocks without subsequent `raise` or `RISK_HALT`.
*   **Evidence**:
    - `core/event_store.py:167,200`: Critical data read failures are caught and logged but not bubbled.
    - `security/jwt_auth.py:89`: Auth failures caught globally without specific handling.
*   **Impact**: "Silent Death" scenarios where the system continues running in a corrupted or orphaned state.

### 6.4 Hardcoding & Magic Numbers (§2.3 / §4.15) — 🔴 FAILED
*   **Finding**: Strategy and execution parameters are hardcoded as literals instead of being pulled from `core/config.py`.
*   **Evidence**:
    - `strategy/ensemble_strategy.py:71,72`: Hardcoded weights `(0.4, 0.3, 0.2, 0.1)` and `decay_penalty=0.5`.
    - `execution/benchmark_orderbook.py:63,65`: Uses literal `0.99`, `1.01`, `0.05`.
*   **Impact**: Configuration changes require code deployment, breaking the "Dynamic Configuration" protocol.

### 6.5 Architectural Circularity Audit — 🟡 WARNING
*   **Finding**: Identified circular dependency patterns between the `ml/` and `ml/pytorch_models` packages.
*   **Evidence**: `ml/__init__.py:17` imports from `ml/pytorch_models`.
*   **Impact**: Unpredictable import side-effects and broken package boundaries.

### 6.6 Concurrency Safety Audit (§2.5 / §37) — 🔴 FAILED
*   **Finding**: Extremely low usage of synchronization primitives (**2 instances of `Lock`** in 404 files).
*   **Evidence**: `core/event_bus.py` accesses shared state without a lock during worker task management.
*   **Impact**: Non-deterministic execution order and potential silent data corruption under high-event-burst HFT scenarios.

### 6.7 De-vectorization Performance Bottlenecks (§2.1 / §4.1) — 🔴 FAILED
*   **Finding**: Conversion from Polars C-buffers back to Python managed heap mid-calculation.
*   **Evidence**: **3 instances** of `.to_list()` or `.to_dicts()` in the `execution/` and `alpha/` layers. 
*   **Impact**: Breaks the "Zero Loop" requirement, introducing latency spikes and garbage collection pressure in the critical path.

### 6.8 Execution Latency Jitter Audit (§2.5 / §5.1) — 🟡 WARNING
*   **Finding**: **111 logging points** (`info`/`debug`) found within the `execution/` sub-millisecond pipeline.
*   **Impact**: Standard Python logging is blocking; 111 points will cause unpredictable latency jitters in high-load scenarios.

---

## 7. STUB METHOD ANALYSIS

~60 methods return hardcoded empty values (`[]`, `{}`, `None`) as fallback paths. While some are valid guard clauses, many indicate **incomplete implementations**.

### High-Risk Stubs (Core Business Logic)

|  File  |  Location  |  Return  |  Risk  |
|:---|:---|:---|:---|
|  `execution/execution_engine.py:77,81,85`  |  3 methods  |  `return {}`  |  🔴 Execution engine stubs  |
|  `execution/routing/router.py:57`  |  route()  |  `return {}`  |  🔴 Router returns empty  |
|  `execution/routing/fill_model.py:50`  |  predict()  |  `return {}`  |  🔴 Fill model stub  |
|  `execution/routing/cost_model.py:55`  |  estimate()  |  `return {}`  |  🔴 Cost model stub  |
|  `execution/routing/liquidity_model.py:48`  |  assess()  |  `return {}`  |  🔴 Liquidity model stub  |
|  `execution/adapters/broker_bridge.py:89`  |  —  |  `return {}`  |  🔴 Broker integration stub  |
|  `meta/orchestrator.py:77`  |  orchestrate()  |  `return {}`  |  🟡 Orphaned anyway  |
|  `strategy/base.py:76`  |  compute_signals()  |  `raise NotImplementedError`  |  ✅ Correct abstract pattern  |

### Medium-Risk Stubs (Supporting Logic)

|  File  |  Return  |  Assessment  |
|:---|:---|:---|
|  `risk/portfolio/hrp.py:37,136`  |  `return {}`  |  🟡 Guard clause for empty input  |
|  `risk/portfolio/kelly.py:77,100`  |  `return {}`  |  🟡 Guard clause  |
|  `alpha/factory.py:72,77,99`  |  `return []`  |  🟡 Guard clause  |
|  `ml/meta_online.py:74,110`  |  `return {}`  |  🟡 Fallback for missing data  |

---

## 6. STANDASH COMPLIANCE MATRIX

Comparing current implementation against each requirement in `standash-document.md`.

### 6.1 Market Data Layer (§4.1)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Feed Arbitration (A/B)  |  ✅  |  `data/market/feed_arbitrator.py`  |  —  |
|  Gap Detection < 1ms  |  ✅  |  `data/pipeline/gap_detector.py`  |  —  |
|  L2/L3 Orderbook Snapshot  |  ✅  |  `data/market/snapshot_recovery.py`  |  Contains sleep violation  |
|  Timestamp Alignment  |  ✅  |  `data/market/clock_sync.py`  |  Contains sleep violation  |
|  Outlier Detection (Z-score/MAD)  |  ✅  |  `data/quality.py`, `data/quality_gate.py`  |  —  |
|  Stale Data Detection  |  ✅  |  `data/quality_gate.py`  |  —  |
|  Cross-exchange Price Sanity  |  ⚠️  |  Partial in quality gate  |  Needs explicit cross-exchange check  |

### 6.2 Alpha Engine (§4.2)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  100% Vectorized (Polars/NumPy)  |  ✅  |  `features/`, `alpha/`  |  —  |
|  No Python loops  |  ✅  |  Verified  |  —  |
|  Point-in-Time Integrity  |  ✅  |  `features/validator.py`  |  —  |

### 6.3 Feature Validation (§4.3)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  IC > 0.02  |  ✅  |  `alpha/ic.py`  |  —  |
|  IC Decay analysis  |  ✅  |  `alpha/decay.py`  |  —  |
|  Auto-disable on Drift (PSI/KS > 15%)  |  ✅  |  `analytics/drift.py`, `drift_detector.py`  |  —  |

### 6.4 Strategy Engine (§4.4)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Probabilistic output  |  ✅  |  `strategy/probabilistic_strategy.py`  |  —  |
|  Dynamic ensemble weighting  |  ✅  |  `strategy/ensemble_strategy.py`  |  —  |

### 6.5 Portfolio Allocator (§4.5)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Risk Parity  |  ✅  |  `risk/portfolio/risk_parity.py`  |  —  |
|  Correlation-aware  |  ✅  |  `risk/portfolio/multi_asset_engine.py`  |  —  |
|  Volatility Targeting  |  ✅  |  Within allocator modules  |  —  |
|  Factor Neutralization  |  ✅  |  `risk/portfolio/factor_neutral.py`  |  —  |
|  Constraint Solver (QP/Convex)  |  ✅  |  `risk/portfolio/optimization.py`  |  —  |
|  **Canonical allocator**  |  🔴  |  **6 competing implementations**  |  **Critical: Which is authoritative?**  |

### 6.6 Risk Engine (§4.6)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Real-time VaR, DD, Leverage  |  ✅  |  `risk/realtime.py` (216 lines)  |  —  |
|  Fat-finger Protection  |  ✅  |  `risk/limits.py`  |  —  |
|  Concentration Limit (5%)  |  ✅  |  `risk/limits.py`  |  —  |
|  Kill Switch < 2s  |  ⚠️  |  `risk/kill_switch.py`  |  **3 competing kill switches**  |
|  Regime-aware Risk Adjustment  |  ✅  |  `risk/regime_adapter.py`  |  Orphaned — never wired  |

### 6.7 Execution Engine (§4.7)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Async non-blocking  |  ✅  |  `execution/execution_engine.py`  |  —  |
|  Idempotent Order ID  |  ✅  |  `execution/order_id.py`  |  **Orphaned — never imported**  |
|  Queue position modeling  |  ⚠️  |  `execution/microstructure/queue_model.py`  |  **Orphaned**  |
|  Hidden liquidity detection  |  ⚠️  |  `execution/microstructure/hidden_liquidity.py`  |  **Orphaned**  |
|  Adverse selection modeling  |  ⚠️  |  `execution/adverse_model.py`  |  **Orphaned**  |
|  Toxic Flow Detection  |  ⚠️  |  `execution/microstructure/toxic_flow.py`  |  **Orphaned**  |
|  Spoofing Detection  |  ⚠️  |  `hft/spoofing.py`  |  **Orphaned**  |
|  Execution Engine core methods  |  🔴  |  Lines 77,81,85 return `{}`  |  **3 stub methods in core engine**  |

### 6.8 Smart Order Router (§4.8)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Micro-price Logic  |  ✅  |  `execution/microstructure/microprice.py`  |  Duplicate exists in `hft/`  |
|  Liquidity Sweeping  |  ⚠️  |  `execution/smart_router.py`  |  Routing sub-modules all orphaned  |

### 6.9 OMS & Reconciliation (§4.9)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Real-time Reconciliation  |  ✅  |  `execution/reconciliation_engine.py`  |  Contains sleep violation  |
|  Periodic Reconciliation (1m)  |  ⚠️  |  Partial  |  Timer-based recon not wired  |
|  Hard Mismatch → Trading Halt  |  ⚠️  |  Present in recon engine  |  Kill switch not connected  |
|  Event Sourcing  |  ✅  |  `core/event_store.py`, `oms/event_store.py`  |  —  |
|  Full Replay Engine  |  ⚠️  |  `oms/replay_engine.py`  |  **Orphaned**  |

### 6.10 HFT & Clock Infrastructure (§4.10)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Clock Synchronization  |  ✅  |  `data/market/clock_sync.py`  |  Sleep violation  |
|  Timestamp Normalization  |  ✅  |  `data/pipeline/normalizer.py`  |  —  |
|  Self-healing / Auto-restart  |  ⚠️  |  `risk/recovery_system.py`  |  Unclear integration  |

### 6.11 MLOps (§4.11)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Model versioning  |  ✅  |  `ml/mlflow_manager.py` (669 lines)  |  —  |
|  Shadow Validation ≥ 7 days  |  ✅  |  `execution/shadow_engine.py`  |  —  |

### 6.12 Capital Accounting (§4.14)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  PnL Separation (Realized/Unrealized)  |  ✅  |  `analytics/accounting.py`  |  Duplicate in `risk/portfolio/accounting.py`  |
|  Funding & Borrowing Tracking  |  ⚠️  |  `portfolio/funding_engine.py`  |  **Orphaned**  |
|  Fee Accrual  |  ✅  |  `analytics/fee_engine.py`  |  Duplicate in `portfolio/fee_engine.py`  |
|  Cash Ledger  |  ⚠️  |  `portfolio/cash_ledger.py`  |  **Orphaned**  |
|  NAV Calculation  |  ⚠️  |  `portfolio/nav_engine.py`  |  **Orphaned**  |

### 6.13 Dynamic Config (§4.15)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Feature Flags  |  ✅  |  `core/config.py`, `core/config_manager.py`  |  —  |
|  Runtime Risk Override  |  ⚠️  |  Present but unclear integration  |  —  |
|  Kill Switch Config  |  ⚠️  |  3 kill switches, unclear which is configurable  |  —  |

### 6.14 Drift Monitoring (§4.12)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  PSI / KS test  |  ✅  |  `analytics/drift.py`, `analytics/drift_detector.py`  |  —  |
|  Auto-retrain trigger  |  ✅  |  `ml/retrain_system.py`  |  —  |

### 6.15 Shadow Mode (§4.13)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Full pipeline shadow  |  ✅  |  `execution/shadow_engine.py` (414 lines)  |  —  |
|  Backtest vs Live comparison  |  ⚠️  |  `monitoring/shadow_compare.py`  |  Needs verification  |

### 6.16 TCA & Execution Analytics (§9)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Implementation Shortfall  |  ⚠️  |  `tca/implementation_shortfall.py`  |  **Orphaned** (entire tca/ module)  |
|  Slippage Decomposition  |  ⚠️  |  `tca/slippage.py`  |  **Orphaned**  |
|  Venue Ranking  |  ⚠️  |  `tca/venue_ranking.py`  |  **Orphaned**  |
|  Active TCA  |  ✅  |  `analytics/tca_engine.py`, `analytics/tca_models.py`  |  These are active but `tca/` is dead  |

### 6.17 Fund Governance (§8)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Approval Process (Research→Shadow→Live)  |  ⚠️  |  `governance/approval_pipeline.py`  |  **Orphaned**  |
|  Model Risk Scoring  |  ⚠️  |  `governance/model_risk.py`  |  **Orphaned**  |
|  Strategy Sandbox  |  ✅  |  `governance/sandbox.py`  |  —  |
|  Strategy FSM  |  ✅  |  `governance/strategy_fsm.py`  |  —  |
|  Human Override Governance  |  ⚠️  |  `security/override_system.py`  |  —  |

### 6.18 Security & Audit (§5.3)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  API Key Encryption  |  ✅  |  `security/secret_manager.py`  |  —  |
|  Audit Trail  |  ✅  |  `audit/audit_store.py`, `audit/audit_storage.py`  |  —  |
|  Secret Rotation  |  ✅  |  `security/key_rotation.py`  |  —  |
|  RBAC  |  ✅  |  `security/rbac.py`  |  —  |
|  Network Isolation  |  ✅  |  `security/network_isolation.py`  |  —  |
|  Audit Export (CSV/FIX)  |  🔴  |  `audit/compliance_exporter.py`  |  **Orphaned**  |
|  Regulatory Reporting  |  🔴  |  `audit/regulatory_export.py`  |  **Orphaned**  |

### 6.19 Data Governance & Compliance (§11)

|  Requirement  |  Status  |  Implementation  |  Gap  |
|:---|:---|:---|:---|
|  Dataset Versioning  |  ✅  |  `data/versioning.py`  |  —  |
|  Feature Lineage  |  ✅  |  `compliance/lineage_tracker.py`  |  —  |
|  Trade Surveillance  |  ✅  |  `compliance/surveillance_engine.py`  |  —  |
|  Position Limits  |  ✅  |  `compliance/position_limiter.py`  |  —  |
|  Spoof Detection  |  ✅  |  `compliance/spoof_detector.py`  |  —  |

### 6.20 Production Readiness Checklist (§12)

|  Checklist Item  |  Status  |  Gap  |
|:---|:---|:---|
|  Real-time Recon Verified  |  ⚠️  |  Recon present but has sleep violation  |
|  Clock Sync Active  |  ⚠️  |  Clock sync present but has sleep violation  |
|  TCA Baseline  |  🔴  |  TCA module entirely orphaned  |
|  HA Failover Test  |  ⚠️  |  `certification/failover_test.py` exists but cert module has no `__init__.py`  |
|  FSM Validation  |  ⚠️  |  2 competing FSM implementations  |

---

## 7. COMPLIANCE SCORECARD SUMMARY

|  Standash Section  |  Requirements  |  Met  |  Partial  |  Gap  |  Score  |
|:---|:---|:---|:---|:---|:---|
|  §4.1 Market Data  |  7  |  5  |  2  |  0  |  86%  |
|  §4.2 Alpha Engine  |  3  |  3  |  0  |  0  |  100%  |
|  §4.3 Feature Validation  |  3  |  3  |  0  |  0  |  100%  |
|  §4.4 Strategy Engine  |  2  |  2  |  0  |  0  |  100%  |
|  §4.5 Portfolio Allocator  |  6  |  5  |  0  |  1  |  83%  |
|  §4.6 Risk Engine  |  5  |  3  |  2  |  0  |  80%  |
|  §4.7 Execution Engine  |  7  |  2  |  4  |  1  |  57%  |
|  §4.8 SOR  |  2  |  1  |  1  |  0  |  75%  |
|  §4.9 OMS & Recon  |  5  |  2  |  3  |  0  |  70%  |
|  §4.10 HFT & Clock  |  3  |  2  |  1  |  0  |  83%  |
|  §4.11 MLOps  |  2  |  2  |  0  |  0  |  100%  |
|  §4.14 Capital Accounting  |  5  |  2  |  3  |  0  |  70%  |
|  §4.15 Dynamic Config  |  3  |  1  |  2  |  0  |  67%  |
|  §8 Fund Governance  |  5  |  2  |  3  |  0  |  70%  |
|  §9 TCA  |  3  |  1  |  2  |  0  |  67%  |
|  §11 Data Governance  |  5  |  5  |  0  |  0  |  100%  |
|  §12 Go-Live Checklist  |  5  |  0  |  4  |  1  |  40%  |
|  **TOTAL**  |  **71**  |  **41**  |  **27**  |  **3**  |  **77%**  |

---

## 8. RISK PRIORITY MATRIX

### 🔴 P0 — Must Fix Before Any Live Trading

|  #  |  Issue  |  Impact  |  Action  |
|:---|:---|:---|:---|
|  1  |  **3 Kill Switch implementations**  |  Capital protection ambiguity  |  Consolidate to single canonical `risk/kill_switch.py`  |
|  2  |  **6 Allocator implementations**  |  Inconsistent position sizing  |  Consolidate under `risk/portfolio/`  |
|  3  |  **Dual Accounting engines**  |  NAV/PnL discrepancy  |  Choose one canonical source  |
|  4  |  **2 Order FSM implementations**  |  State machine divergence  |  Remove `execution/order_fsm.py`  |
|  5  |  **Execution engine stub methods**  |  Orders route to empty `{}`  |  Implement real logic at lines 77,81,85  |
|  6  |  **11 packages missing `__init__.py`**  |  60+ files unimportable  |  Create all missing `__init__.py`  |
|  7  |  **Institutional Compliance Gap**  |  No live regulatory/audit export  |  Wire `audit/compliance_exporter.py`  |

### 🟡 P1 — Must Fix Before Shadow Mode

|  #  |  Issue  |  Impact  |  Action  |
|:---|:---|:---|:---|
|  7  |  **80 orphaned modules**  |  Dead code, maintenance burden  |  Audit each; integrate or delete  |
|  8  |  **Sleep violations** in production code  |  Latency, blocking I/O  |  Replace with event-driven patterns  |
|  9  |  **TCA module entirely orphaned**  |  No execution analytics  |  Wire `tca/` or delete in favor of `analytics/tca_*`  |
|  10  |  **Routing sub-modules all return `{}`**  |  Smart routing non-functional  |  Implement fill/cost/liquidity models  |

### 🟢 P2 — Should Fix Before Production

|  #  |  Issue  |  Impact  |  Action  |
|:---|:---|:---|:---|
|  11  |  **Duplicate microstructure code**  |  hft/ vs execution/microstructure/  |  Consolidate under one canonical location  |
|  12  |  **meta/ module 87% orphaned**  |  Wasted complexity  |  Evaluate if meta-learning is needed; prune  |
|  13  |  **3 Binance adapter implementations**  |  Connector confusion  |  Keep `execution/brokers/binance.py`, delete duplicates  |
|  14  |  **4 Orderbook implementations**  |  Maintenance overhead  |  Consolidate to `orderbook_enhanced.py`  |
|  15  |  **Regime detection 3-way split**  |  Model selection confusion  |  Consolidate under `ml/regime.py`  |

---

## 9. RECOMMENDED CONSOLIDATION PLAN

### Phase 1: Structural Integrity (Days 1-3)

```
1. Create all 11 missing __init__.py files
2. Establish canonical modules:
   - Kill Switch    → risk/kill_switch.py (single source of truth)
   - Order FSM      → oms/order_fsm.py (single source of truth)
   - Accounting     → analytics/accounting.py (single source of truth)
   - Fee Engine     → analytics/fee_engine.py (single source of truth)
   - Allocator      → risk/portfolio/allocator.py (consolidated)
3. Wire orphaned-but-needed modules:
   - execution/order_id.py → import in execution engine
   - risk/regime_adapter.py → import in risk engine
```

### Phase 2: Dead Code Removal (Days 4-6)

```
1. Delete all duplicate orphans (files that have a canonical counterpart):
   - governance/kill_switch.py (→ risk/kill_switch.py exists)
   - execution/order_fsm.py (→ oms/order_fsm.py exists)
   - execution/exchange/* (→ execution/brokers/* exists)
   - execution/adapters/* (→ execution/brokers/* exists)
   - hft/microprice.py (→ execution/microstructure/microprice.py exists)
   - hft/imbalance.py (→ execution/microstructure/imbalance.py exists)
   - tca/* (→ analytics/tca_* exists)
2. Evaluate meta/ module: keep only orchestrator.py, strategy_generator.py if used
3. Prune portfolio/ duplicates that overlap with risk/portfolio/
```

### Phase 3: Stub Completion (Days 7-10)

```
1. Implement execution_engine.py stub methods (lines 77,81,85)
2. Implement execution/routing/ sub-module logic
3. Wire microstructure modules into execution pipeline
4. Remove all asyncio.sleep/time.sleep from production code paths
```

### Phase 4: Integration Testing (Days 11-14)

```
1. Validate single canonical path for each critical flow:
   Signal → Risk Gate → Allocator → SOR → Exchange → Recon → PnL
2. End-to-end shadow mode test with unified modules
3. Kill switch integration test (single trigger point)
4. Reconciliation loop without sleep violations
```

---

## 10. FILE COUNT BY MODULE

|  Module  |  Total Files  |  Orphaned  |  Active  |  Health  |
|:---|:---|:---|:---|:---|
|  `alpha/`  |  16  |  0  |  16  |  🟢  |
|  `analytics/`  |  11  |  0  |  11  |  🟢  |
|  `api/`  |  1  |  0  |  1  |  🟢  |
|  `audit/`  |  8  |  5  |  3  |  🟡  |
|  `backtest/`  |  9  |  4  |  5  |  🟡  |
|  `bot/`  |  5  |  0  |  5  |  🟢  |
|  `certification/`  |  13  |  —  |  —  |  ⚠️ No `__init__.py`  |
|  `compliance/`  |  5  |  0  |  5  |  🟢  |
|  `core/`  |  17  |  2  |  15  |  🟢  |
|  `data/`  |  19  |  0  |  19  |  🟢  |
|  `execution/`  |  46  |  22+  |  ~24  |  🔴  |
|  `features/`  |  11  |  1  |  10  |  🟢  |
|  `feedback/`  |  2  |  2  |  0  |  🔴  |
|  `governance/`  |  6  |  2  |  4  |  🟡  |
|  `hft/`  |  8  |  5  |  3  |  🔴  |
|  `meta/`  |  15  |  13  |  2  |  🔴  |
|  `ml/`  |  17  |  3  |  14  |  🟡  |
|  `models/`  |  3  |  1  |  2  |  🟡  |
|  `monitoring/`  |  9  |  0  |  9  |  🟢  |
|  `oms/`  |  7  |  3  |  4  |  🟡  |
|  `pipeline/`  |  4  |  2  |  2  |  🟡  |
|  `portfolio/`  |  14  |  7+  |  ~7  |  🔴  |
|  `research/`  |  4  |  1  |  3  |  🟡  |
|  `risk/`  |  25  |  0*  |  25  |  🟢  |
|  `security/`  |  8  |  0  |  8  |  🟢  |
|  `strategy/`  |  14  |  0  |  14  |  🟢  |
|  `system/`  |  2  |  2  |  0  |  🔴  |
|  `tca/`  |  6  |  6  |  0  |  🔴  |
|  `utils/`  |  1  |  0  |  1  |  🟢  |
|  `validation/`  |  5  |  0  |  5  |  🟢  |

---

## APPENDIX A: COMPLETE ORPHAN LIST

<details>
<summary>Click to expand full list of 80 orphaned files</summary>

```
qtrader/research/walkforward.py
qtrader/oms/interface.py
qtrader/oms/replay_engine.py
qtrader/oms/oms_multi_adapter.py
qtrader/pipeline/deployment.py
qtrader/pipeline/session_bridge.py
qtrader/tca/venue_ranking.py
qtrader/tca/cost_attribution.py
qtrader/tca/implementation_shortfall.py
qtrader/tca/tca_report.py
qtrader/tca/slippage.py
qtrader/tca/benchmark.py
qtrader/core/event_validator.py
qtrader/core/event_bus_adapter.py
qtrader/features/technical/indicators.py
qtrader/meta/genetic.py
qtrader/meta/self_diagnostic.py
qtrader/meta/memory.py
qtrader/meta/governance_engine.py
qtrader/meta/risk_filter.py
qtrader/meta/deployment_pipeline.py
qtrader/meta/multi_agent.py
qtrader/meta/lifecycle_manager.py
qtrader/meta/audit_logger.py
qtrader/meta/research_loop.py
qtrader/meta/approval_system.py
qtrader/meta/shadow_enforcer.py
qtrader/meta/self_evolution.py
qtrader/meta/constraint_engine.py
qtrader/models/catboost_model.py
qtrader/feedback/incident_handler.py
qtrader/feedback/dashboard.py
qtrader/backtest/l2_broker_sim.py
qtrader/backtest/walk_forward_bt.py
qtrader/backtest/tick_engine.py
qtrader/backtest/multi_asset.py
qtrader/system/system_orchestrator.py
qtrader/system/pipeline_validator.py
qtrader/audit/replay_audit.py
qtrader/audit/regulatory_export.py
qtrader/audit/dashboard.py
qtrader/audit/trade_audit.py
qtrader/audit/compliance_exporter.py
qtrader/ml/regime_detector.py
qtrader/ml/model_comparator.py
qtrader/ml/hmm_regime.py
qtrader/execution/benchmark_orderbook.py
qtrader/execution/adverse_model.py
qtrader/execution/execution_monitor.py
qtrader/execution/microstructure/queue_model.py
qtrader/execution/microstructure/toxic_flow.py
qtrader/execution/microstructure/spread_model.py
qtrader/execution/microstructure/hidden_liquidity.py
qtrader/execution/exchange/binance_adapter.py
qtrader/execution/exchange/coinbase_adapter.py
qtrader/execution/reconciliation_service.py
qtrader/execution/degradation_handler.py
qtrader/execution/order_id.py
qtrader/execution/state_builder.py
qtrader/execution/adapters/binance_adapter.py
qtrader/execution/adapters/broker_bridge.py
qtrader/execution/retry_handler.py
qtrader/execution/rl_agent.py
qtrader/execution/rl/reward.py
qtrader/execution/execution_quality.py
qtrader/execution/strategy/slicing.py
qtrader/execution/strategy/scheduler.py
qtrader/execution/slippage_control.py
qtrader/hft/queue_model.py
qtrader/hft/spoofing.py
qtrader/hft/toxic_flow.py
qtrader/hft/market_maker.py
qtrader/hft/rl_agent.py
qtrader/governance/model_risk.py
qtrader/governance/approval_pipeline.py
qtrader/portfolio/risk_monitor.py
qtrader/portfolio/funding_engine.py
qtrader/portfolio/scaling_governor.py
qtrader/portfolio/position_sizing.py
qtrader/portfolio/cash_ledger.py
qtrader/portfolio/nav_engine.py
qtrader/portfolio/capital_flow.py
qtrader/portfolio/drawdown_controller.py
qtrader/portfolio/fee_engine.py
```

</details>

---

> [!CAUTION]
> **BOTTOM LINE**: The QTrader codebase has ~77% of standash requirements implemented in isolation, but only ~55% are properly integrated into a working system. The primary blocker is not missing features — it's **architectural fragmentation**. The system cannot be trusted for live trading until the 18 duplicate clusters are resolved, the 80 orphaned modules are either connected or pruned, and the 11 broken packages are fixed. The code exists; the wiring does not.
