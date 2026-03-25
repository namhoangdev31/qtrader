# QTRADER — SYSTEM GAP ANALYSIS & UPGRADE BLUEPRINT

> **Ngày phân tích:** 2026-03-25  
> **Phiên bản hệ thống:** v0.1.0  
> **Tham chiếu chuẩn:** [`standash-document.md`](./standash-document.md) (Tier-1 Institutional Hedge Fund Grade)  
> **Phương pháp:** Deep scan toàn bộ source tree + so sánh 1-1 với từng Hard Requirement trong standash.

---

## LEGEND (Ký hiệu đánh giá)

| Ký hiệu         | Ý nghĩa                                  |
| --------------- | ---------------------------------------- |
| ✅ **DONE**     | Đã triển khai đầy đủ, đạt chuẩn          |
| ⚠️ **PARTIAL**  | Có skeleton/stub nhưng chưa hoàn thiện   |
| ❌ **MISSING**  | Chưa tồn tại hoặc chỉ là interface rỗng  |
| 🔥 **CRITICAL** | Lỗi nghiêm trọng vi phạm Core Principles |

---

## 1. EXECUTIVE SUMMARY — ĐIỂM YẾU HỆ THỐNG

Sau khi quét toàn bộ **25 module**, **~150 source files**, đối chiếu từng điều khoản trong `standash-document.md`, hệ thống QTrader hiện tại ở trạng thái:

> **GRADE: Pre-Alpha Production — NOT READY FOR LIVE TRADING**

### Tóm tắt điểm yếu nghiêm trọng nhất

| #   | Khu vực                 | Mức độ      | Vấn đề cốt lõi                                                                                                       |
| --- | ----------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------- |
| 1   | OMS                     | 🔥 CRITICAL | `qtrader/oms/` chỉ có 1 file `interface.py` — abstract class thuần túy, **không có implementation**                  |
| 2   | Reconciliation          | 🔥 CRITICAL | `reconciliation_engine.py` (51 dòng) không có auto-halt, không có trigger Trading Halt khi mismatch                  |
| 3   | Shadow Engine           | 🔥 CRITICAL | `shadow.py` là 30-dòng stub: **không tính PnL**, **không so sánh backtest vs live**                                  |
| 4   | Zero-Latency Violations | 🔥 CRITICAL | `asyncio.sleep(0.01)` hardcode trong main orchestrator loop (line 714); `asyncio.sleep` trong WarRoom broadcast loop |
| 5   | Security/RBAC           | ❌ MISSING  | `security/rbac.py` là 45-dòng enum, không có middleware enforcement, không có JWT integration                        |
| 6   | Monitoring / War Room   | ❌ MISSING  | Không có Latency Heatmap, không có Order Lifecycle Trace, không có Exchange Health Dashboard                         |
| 7   | Feed Arbitration        | ❌ MISSING  | Không có A/B Feed Arbitrator, không có PTP/NTP clock sync                                                            |
| 8   | Capital Accounting      | ⚠️ PARTIAL  | Không có NAV real-time, không có Multi-currency Cash Ledger, không có Funding/Borrowing tracking                     |
| 9   | TCA Engine              | ❌ MISSING  | Không có Transaction Cost Analysis module nào hoàn chỉnh                                                             |
| 10  | HA / Failover           | ❌ MISSING  | Không có Active/Active hoặc Active/Passive failover, không có Stateful Replication                                   |

---

## 2. PHÂN TÍCH CHI TIẾT THEO LAYER

---

### 2.1 MARKET DATA LAYER (L3 STANDARD) — §4.1

#### Files liên quan

- `qtrader/data/quality_gate.py` (166 lines)
- `qtrader/data/market/` (chưa scan sâu — cần kiểm tra)
- `qtrader/data/quality.py`, `catalog.py`, `lineage.py`

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.1)             | Trạng thái | Chi tiết                                                                                 |
| ----------------------------------- | ---------- | ---------------------------------------------------------------------------------------- |
| Feed Arbitration (A/B feeds)        | ❌ MISSING | Không có `feed_arbitrator.py` nào trong toàn bộ codebase                                 |
| Sequence ID Gap Detection < 1ms     | ⚠️ PARTIAL | `check_sequence_gap()` có trong quality_gate nhưng không tích hợp vào live feed pipeline |
| Orderbook Snapshot L2/L3 Recovery   | ⚠️ PARTIAL | `orderbook_enhanced.py` (18KB) tồn tại nhưng không có snapshot recovery flow             |
| Timestamp Alignment / Normalization | ❌ MISSING | Không có Clock Sync module, không có PTP/NTP adapter                                     |
| Outlier Detection (Z-score / MAD)   | ⚠️ PARTIAL | Z-score có trong `quality_gate.py`, **MAD (Median Absolute Deviation) chưa có**          |
| Stale Data Detection                | ✅ DONE    | `check_stale()` triển khai trong `quality_gate.py`                                       |
| Cross-exchange Price Sanity         | ✅ DONE    | `check_cross_exchange_sanity()` triển khai trong `quality_gate.py`                       |
| Trade/Quote Mismatch Check          | ❌ MISSING | Không có logic kiểm tra sự logic giữa order và fill                                      |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `qtrader/data/feed_arbitrator.py` — Arbitrate A/B feeds, detect sequence gaps in < 1ms using monotonic clock, publish to internal event bus
- **[NEW]** `qtrader/data/clock_sync.py` — PTP/NTP adapter, expose `get_exchange_aligned_timestamp(exchange_id)` → `datetime`
- **[MODIFY]** `quality_gate.py` — Thêm `check_outlier(method="mad")`, thêm `check_trade_quote_mismatch()`
- **[MODIFY]** market data pipeline — Tích hợp `DataQualityGate` trước mỗi alpha calculation, raise `TradingHalt` event nếu fail

---

### 2.2 ALPHA ENGINE / FEATURE FACTORY — §4.2 & §4.3

#### Files liên quan

- `qtrader/alpha/` — 16 files (base, combiner, decay, ensemble_model, factor_model, factory, ic, registry, etc.)
- `qtrader/features/` — store.py (10KB), registry.py (5KB), base.py, engine.py, neutralization.py, + 4 subdirs

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.2/4.3)                     | Trạng thái | Chi tiết                                                                                                                                   |
| ----------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 100% Vectorized (Polars/NumPy), No Python loops | ✅ DONE    | Codebase dùng Polars, không thấy `df.iloc` trong loops                                                                                     |
| Point-in-Time Integrity (No Look-ahead bias)    | ⚠️ PARTIAL | Tests yêu cầu look-ahead bias check nhưng coverage chưa đo được                                                                            |
| IC > 0.02 validation                            | ✅ DONE    | `alpha/ic.py` có IC computation                                                                                                            |
| IC Decay Analysis                               | ✅ DONE    | `alpha/decay.py` tồn tại                                                                                                                   |
| Feature Drift (PSI/KS) Auto-Disable             | ⚠️ PARTIAL | `analytics/drift_detector.py` tồn tại nhưng **kết nối với auto-disable pipeline chưa hoàn chỉnh** (chỉ log warning, không disable feature) |
| Dataset Versioning                              | ✅ DONE    | `data/versioning.py` tồn tại                                                                                                               |
| Feature Lineage                                 | ✅ DONE    | `data/lineage.py` tồn tại                                                                                                                  |

#### Kỹ thuật yêu cầu để nâng cấp

- **[MODIFY]** `alpha/factory.py` — Khi `drift_detector` phát hiện PSI > 15%, gọi `registry.disable_feature(name)` thay vì chỉ log
- **[NEW]** `features/pit_validator.py` — Explicit Point-in-Time guard: kiểm tra `df[i]` không dùng data từ `df[i+1:]`
- **[MODIFY]** `core/orchestrator.py` — Thay `alphas` đơn lẻ loop bằng `feature_factory.compute_batch()` để giảm latency

---

### 2.3 STRATEGY ENGINE — §4.4

#### Files liên quan

- `qtrader/strategy/` — 14 files (probabilistic_strategy, ensemble_strategy, regime_meta_strategy, momentum, mean_reversion, etc.)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.4)                               | Trạng thái | Chi tiết                                                                                                                |
| ----------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------- |
| Probabilistic Output (BUY/SELL/HOLD với xác suất)     | ✅ DONE    | `probabilistic_strategy.py` (9KB) đầy đủ                                                                                |
| Ensemble với Dynamic Weighting (24h/7d)               | ⚠️ PARTIAL | `ensemble_strategy.py` (14KB) tồn tại nhưng weight update dựa trên hardcoded `regime="default"` (orchestrator line 447) |
| Strategy Sandbox Isolation                            | ❌ MISSING | Không có process isolation, không có per-strategy capital limits, không có fault barrier                                |
| Strategy Lifecycle (Research → Paper → Shadow → Live) | ⚠️ PARTIAL | Không có formal approval gate, shadow mode là stub                                                                      |
| Kill Model không Kill System                          | ⚠️ PARTIAL | NetworkKillSwitch kill toàn bộ system, không có model-level kill                                                        |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `strategy/sandbox.py` — StrategySandbox: isolated capital counter + circuit breaker per strategy
- **[MODIFY]** `strategy/ensemble_strategy.py` — Weight update phải dùng rolling performance window (24h/7d), không hardcode regime
- **[NEW]** `strategy/lifecycle.py` — State machine: `RESEARCH` → `PAPER` → `SHADOW` → `COMMITTEE_REVIEW` → `LIVE` → `SUSPENDED`
- **[MODIFY]** `risk/network_kill_switch.py` — Thêm `kill_strategy(strategy_id)` không ảnh hưởng hệ thống khác

---

### 2.4 PORTFOLIO ALLOCATOR — §4.5

#### Files liên quan

- `qtrader/portfolio/` — 14 files (accounting, allocator, capital_allocator, factor_neutral, hrp, kelly, risk_parity, multi_asset_engine, etc.)
- `qtrader/risk/portfolio_allocator.py` + `portfolio_allocator_enhanced.py`

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.5)                              | Trạng thái | Chi tiết                                                                                                                  |
| ---------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------- |
| Risk Parity thực thụ                                 | ✅ DONE    | `portfolio/risk_parity.py` (4.9KB) tồn tại                                                                                |
| Correlation-aware Allocation                         | ✅ DONE    | HRP trong `hrp.py` (7KB)                                                                                                  |
| Volatility Targeting                                 | ⚠️ PARTIAL | `risk/volatility.py` tồn tại nhưng tích hợp vào pipeline chưa rõ                                                          |
| Factor Neutralization (Beta neutral, Market neutral) | ✅ DONE    | `portfolio/factor_neutral.py`, `features/neutralization.py`                                                               |
| Exposure Decomposition (by Sector/Factor)            | ⚠️ PARTIAL | `risk/exposure.py` (3.2KB), `risk/factor_risk.py` (5.7KB) — tồn tại nhưng kết nối với portfolio output chưa được verified |
| QP / Convex Optimization Constraint Solver           | ⚠️ PARTIAL | `portfolio/optimization.py` (1.9KB — rất mỏng), `portfolio/optimizer.py` (0.7KB — 1 dòng gần như rỗng)                    |

#### Kỹ thuật yêu cầu để nâng cấp

- **[MODIFY]** `portfolio/optimization.py` — Triển khai đầy đủ Quadratic Programming dùng `scipy.optimize.minimize` với constraint matrix
- **[REPLACE]** `portfolio/optimizer.py` — Xóa stub, merge với `optimization.py`
- **[NEW]** `portfolio/exposure_pipeline.py` — Kết nối `factor_risk.py` → `allocator.py` → output factor-decomposed risk report

---

### 2.5 RISK ENGINE — §4.6 (CRITICAL CORE)

#### Files liên quan

- `qtrader/risk/` — 17 files (realtime, runtime, limits, drawdown_control, feature_validation, network_kill_switch, regime_adapter, etc.)
- `qtrader/risk/runtime_risk_engine.py` (22.5KB — file lớn nhất trong risk/)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.6)                 | Trạng thái | Chi tiết                                                                                      |
| --------------------------------------- | ---------- | --------------------------------------------------------------------------------------------- |
| Real-time VaR, Drawdown, Leverage       | ✅ DONE    | `runtime_risk_engine.py` + `realtime.py` tồn tại                                              |
| Fat-finger Protection                   | ✅ DONE    | `risk/limits.py` (8.7KB) có Fat-finger checks                                                 |
| Concentration Limit (max 5% per symbol) | ✅ DONE    | `limits.py`                                                                                   |
| Kill Switch (`kill_switch()`)           | ✅ DONE    | `network_kill_switch.py` (5.5KB)                                                              |
| Regime-aware Risk Adjustment            | ✅ DONE    | `risk/regime_adapter.py` (3.2KB)                                                              |
| Capital Preservation / War Mode         | ❌ MISSING | Không có explicit `WarMode` state machine — chỉ có kill switch, không có Hedging/Unwind logic |
| HMM Regime → Auto Strategy Deactivation | ⚠️ PARTIAL | Logic tồn tại trong `ml/regime_detector.py` nhưng kết nối với risk engine chưa đầy đủ         |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `risk/war_mode.py` — `WarMode` FSM: Trigger → Stop New Positions → Reduce Exposure 50% → Hedge Only → Full Unwind
- **[MODIFY]** `risk/regime_adapter.py` — Kết nối với `strategy/lifecycle.py` để auto-deactivate strategies trong extreme regime

---

### 2.6 EXECUTION ENGINE — §4.7

#### Files liên quan

- `qtrader/execution/` — 31 files (execution_engine.py 27KB, orderbook_enhanced.py 18KB, smart_router.py 14KB, shadow_engine.py 13KB, oms_adapter.py 10KB, reconciliation_service.py 11KB, adverse_model.py, slippage_model.py, etc.)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.7)                              | Trạng thái | Chi tiết                                                                                 |
| ---------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------- |
| Async non-blocking                                   | ✅ DONE    | Toàn bộ execution dùng `async/await`                                                     |
| Global Unique Order ID (UUID + Exchange + Timestamp) | ✅ DONE    | `execution/order_id.py` (3KB)                                                            |
| Idempotent Order ID (Replay-safe)                    | ✅ DONE    | order_id.py                                                                              |
| Queue Position Modeling                              | ✅ DONE    | `hft/queue_model.py` (2.6KB)                                                             |
| Hidden Liquidity Detection                           | ⚠️ PARTIAL | `execution/orderbook_enhanced.py` có logic nhưng chưa có explicit hidden liquidity model |
| Adverse Selection Modeling                           | ✅ DONE    | `execution/adverse_model.py` (2.4KB), `hft/toxic_flow.py` (2.9KB)                        |
| Toxic Flow Detection                                 | ✅ DONE    | `hft/toxic_flow.py`                                                                      |
| Orderbook Spoofing Detection                         | ✅ DONE    | `hft/spoofing.py` (3KB)                                                                  |
| Quote Stuffing Detection                             | ❌ MISSING | Không có explicit quote stuffing detector                                                |
| Adverse Selection Probability Model                  | ✅ DONE    | `execution/adverse_model.py`                                                             |

---

### 2.7 SMART ORDER ROUTER (SOR) — §4.8

#### Files liên quan

- `qtrader/execution/sor.py` (4.4KB)
- `qtrader/execution/sor_microprice.py` (4.4KB)
- `qtrader/execution/smart_router.py` (13.7KB)
- `qtrader/hft/microprice.py` (2.4KB)
- `qtrader/hft/imbalance.py` (4KB)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.8)                               | Trạng thái   | Chi tiết                                                                          |
| ----------------------------------------------------- | ------------ | --------------------------------------------------------------------------------- |
| Micro-price Logic + Orderbook Imbalance               | ✅ DONE      | `sor_microprice.py` + `hft/microprice.py` + `hft/imbalance.py` — fully vectorized |
| Liquidity Sweeping (split across venues/pools)        | ⚠️ PARTIAL   | `smart_router.py` (13.7KB) tồn tại nhưng chưa rõ multi-venue sweep logic          |
| SOR — File trùng lặp: `sor.py` vs `sor_microprice.py` | 🔥 REDUNDANT | Cả 2 file cùng ~4.4KB, logic gần giống nhau — **tốn bảo trì, gây confusion**      |
| `execution/microprice.py` vs `hft/microprice.py`      | 🔥 REDUNDANT | **Hai file microprice** tồn tại ở hai module khác nhau — ai dùng cái nào?         |

#### Kỹ thuật yêu cầu để nâng cấp

- **[DELETE]** `execution/microprice.py` — Consolidate vào `hft/microprice.py`
- **[MERGE]** `execution/sor.py` → `execution/sor_microprice.py` — Rename thành `execution/sor.py` duy nhất
- **[MODIFY]** `smart_router.py` — Thêm explicit multi-venue order splitting với liquidity weighting

---

### 2.8 OMS & POSITION RECONCILIATION — §4.9 (CRITICAL GAP)

#### Files liên quan

- `qtrader/oms/interface.py` (66 lines — **ONLY FILE IN OMS/!**)
- `qtrader/execution/reconciliation_engine.py` (51 lines)
- `qtrader/execution/reconciliation_service.py` (11KB)
- `qtrader/execution/oms.py` (8.6KB), `oms_adapter.py` (10.6KB), `oms_multi_adapter.py` (8.7KB)
- `qtrader/execution/order_fsm.py` (4.7KB)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.9)                                                  | Trạng thái  | Chi tiết                                                                                                             |
| ------------------------------------------------------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------- |
| **OMS có Implementation**                                                | 🔥 CRITICAL | `qtrader/oms/` chỉ có `interface.py` — abstract class. `execution/oms.py` là implementation nhưng **nằm sai module** |
| FSM States: NEW → ACK → PARTIALLY_FILLED → FILLED → CANCELLED → REJECTED | ✅ DONE     | `execution/order_fsm.py` (4.7KB)                                                                                     |
| Idempotent State Transitions                                             | ✅ DONE     | `order_fsm.py`                                                                                                       |
| Pending Timeout + Auto-Reconcile                                         | ⚠️ PARTIAL  | `order_fsm.py` tồn tại nhưng timeout handling chưa rõ                                                                |
| Real-time Reconciliation (per-Fill)                                      | ⚠️ PARTIAL  | `reconciliation_engine.py` (51 lines) chỉ compare dicts — **không có auto-halt trigger**                             |
| Periodic Reconciliation (1m frequency)                                   | ⚠️ PARTIAL  | `reconciliation_service.py` (11KB) tồn tại — chưa verify integration                                                 |
| Hard Mismatch → Trading Halt                                             | 🔥 CRITICAL | `reconciliation_engine.py` chỉ trả về `"MISMATCH"` string — **không trigger Trading Halt event**                     |
| Event Sourcing & Full Replay Engine                                      | ❌ MISSING  | Không có Event Log store, không có Replay engine                                                                     |
| Stateful OMS Replication                                                 | ❌ MISSING  | Không có node replication infrastructure                                                                             |

#### Kỹ thuật yêu cầu để nâng cấp

- **[MOVE]** `execution/oms.py` → `qtrader/oms/order_management_system.py` — implement đầy đủ `OMSInterface`
- **[MODIFY]** `reconciliation_engine.py` — Thêm: khi `status == "MISMATCH"`, publish `EventType.TRADING_HALT` lên event bus và log với Trace ID
- **[NEW]** `oms/event_store.py` — Append-only event log (DuckDB backend): persist mọi order event + fill event
- **[NEW]** `oms/replay_engine.py` — Rebuild OMS state từ event log từ timestamp T
- **[MODIFY]** `execution/order_fsm.py` — Thêm max timeout per state, trigger `auto_reconcile()` khi Pending > threshold

---

### 2.9 HFT & CLOCK INFRASTRUCTURE — §4.10

#### Files liên quan

- `qtrader/hft/` — 8 files (optimizer.py 19KB, rl_agent.py, market_maker.py, queue_model.py, microprice.py, imbalance.py, toxic_flow.py, spoofing.py)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.10)                | Trạng thái | Chi tiết                                                                     |
| --------------------------------------- | ---------- | ---------------------------------------------------------------------------- |
| Clock Synchronization (PTP/NTP)         | ❌ MISSING | Không có clock sync module. Orchestrator dùng `datetime.utcnow()` không sync |
| Timestamp Normalization (drift < 1ms)   | ❌ MISSING | Không có drift detection hoặc clock alignment                                |
| CPU Core Isolation / Pinning            | ❌ MISSING | Không có CPU affinity configuration                                          |
| HFT Optimizer                           | ✅ DONE    | `hft/optimizer.py` (19KB — largest in HFT)                                   |
| Market Maker Logic                      | ✅ DONE    | `hft/market_maker.py` (3KB)                                                  |
| Self-healing Auto-restart               | ⚠️ PARTIAL | Docker Compose `restart: always` nhưng không có Gradual Recovery             |
| Gradual Recovery (step-by-step restart) | ❌ MISSING | Không có component-level recovery — restart là all-or-nothing                |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `qtrader/data/clock_sync.py` — NTP polling + monotonic clock correction, expose `now_ns()` → `int` (nanoseconds)
- **[NEW]** `core/health_manager.py` — Component health registry, gradual restart sequence: DataFeed → Risk → Execution → Strategy
- **[MODIFY]** `main.py` — Thay `asyncio.sleep(0.01)` bằng event-driven wakeup từ `event_bus`

---

### 2.10 MLOPS & SHADOW MODE — §4.11 & §4.13

#### Files liên quan

- `qtrader/ml/` — 17 files (mlflow_manager.py 28KB, regime_detector.py 18KB, meta_learning_engine.py 12KB, meta_online.py 11KB, evaluation, walk_forward, etc.)
- `qtrader/execution/shadow.py` (30 lines — STUB)
- `qtrader/execution/shadow_engine.py` (12.6KB)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.11/4.13)                 | Trạng thái  | Chi tiết                                                                                                           |
| --------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------ |
| MLflow Model Versioning + Experiment Tracking | ✅ DONE     | `ml/mlflow_manager.py` (28KB) — rất đầy đủ                                                                         |
| Shadow Mode ≥ 7 ngày bắt buộc                 | ❌ MISSING  | Không có minimum duration enforcement. `shadow.py` là stub 30 dòng                                                 |
| Shadow PnL Calculation                        | 🔥 CRITICAL | `shadow.py` có comment `# Logic to calculate shadow fills and pnl...` — **chưa có code thực**                      |
| Shadow vs Live Comparison (daily)             | ❌ MISSING  | Không có daily comparison job                                                                                      |
| Full Pipeline Shadow (không chỉ log signals)  | ⚠️ PARTIAL  | `shadow_engine.py` (12.6KB) có simulation logic nhưng có 2 shadow files (confusion: shadow.py vs shadow_engine.py) |
| Drift Auto-Retrain                            | ⚠️ PARTIAL  | DriftDetector có trong orchestrator nhưng trigger retrain chưa tự động                                             |

#### Kỹ thuật yêu cầu để nâng cấp

- **[DELETE]** `execution/shadow.py` (stub 30 dòng) — dùng `shadow_engine.py` làm single source of truth
- **[MODIFY]** `shadow_engine.py` — Thêm: (1) minimum 7-day enforcement; (2) daily PnL comparison vs live; (3) tolerance threshold để auto-promote strategy to live
- **[NEW]** `ml/retrain_scheduler.py` — Khi `drift_detector.severity > MEDIUM`, schedule retrain job với MLflow experiment lock
- **[MODIFY]** Orchestrator — Kết nối drift result → retrain_scheduler, không chỉ log warning

---

### 2.11 CAPITAL ACCOUNTING LAYER — §4.14

#### Files liên quan

- `qtrader/portfolio/accounting.py` (8.9KB)
- `qtrader/portfolio/fees.py` (7.3KB)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.14)                 | Trạng thái | Chi tiết                                                      |
| ---------------------------------------- | ---------- | ------------------------------------------------------------- |
| PnL Separation (Realized vs Unrealized)  | ⚠️ PARTIAL | `accounting.py` tồn tại nhưng chưa rõ precision của phân tách |
| Funding & Borrowing Cost Tracking        | ❌ MISSING | Không có Funding Rate tracker, không có Margin Cost tracking  |
| Fee Accrual (Maker/Taker + Funding Rate) | ⚠️ PARTIAL | `fees.py` (7.3KB) tồn tại nhưng Funding Rate chưa rõ          |
| Multi-currency Cash Ledger               | ❌ MISSING | Không có Cash Ledger module                                   |
| NAV Real-time Calculation                | ❌ MISSING | Không có NAV computation engine                               |
| EOD Position Snapshot                    | ❌ MISSING | Không có end-of-day reconciliation job                        |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `portfolio/cash_ledger.py` — Multi-currency ledger, FX conversion, cash balance per account
- **[NEW]** `portfolio/nav_engine.py` — NAV = Cash + MarkToMarket(positions), update realtime on fill events
- **[MODIFY]** `portfolio/accounting.py` — Thêm `funding_cost` và `borrowing_cost` fields vào PnL breakdown
- **[NEW]** `portfolio/eod_snapshot.py` — Triggered at EOD via event (không dùng sleep/cron), persist to DuckDB

---

### 2.12 DYNAMIC CONFIG SYSTEM — §4.15

#### Files liên quan

- `qtrader/core/config.py` (5.2KB)
- `configs/bot_paper.yaml`, `configs/bot_prod.yaml`, `configs/execution.yaml`

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §4.15)                       | Trạng thái | Chi tiết                                                       |
| ---------------------------------------------- | ---------- | -------------------------------------------------------------- |
| Feature Flags (toggle strategy không redeploy) | ❌ MISSING | Config là static YAML, không có runtime toggle                 |
| Runtime Risk Override                          | ❌ MISSING | Không có hot-reload mechanism                                  |
| Exchange Routing Config                        | ⚠️ PARTIAL | `configs/execution.yaml` tồn tại nhưng static                  |
| Kill Switch Config (Global + Symbol-level)     | ⚠️ PARTIAL | NetworkKillSwitch tồn tại nhưng không configurable via runtime |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `core/feature_flags.py` — Redis-backed (hoặc DuckDB) feature flag store, `is_enabled(flag_name)` với hot-reload
- **[MODIFY]** `core/config.py` — Thêm `watch_config()` coroutine để reload YAML khi file thay đổi
- **[NEW]** `api/config_api.py` — REST endpoint: `POST /config/risk/{param}`, `POST /config/flags/{name}`

---

### 2.13 MONITORING & WAR ROOM — §5.4

#### Files liên quan

- `qtrader/monitoring/` — 3 files: `api.py` (2.4KB), `metrics.py` (4.5KB), `warroom_service.py` (4KB)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §5.4)                     | Trạng thái | Chi tiết                                                                                      |
| ------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------- |
| Live PnL & VaR Dashboard                    | ⚠️ PARTIAL | `warroom_service.py` có `get_dashboard_snapshot()` nhưng không có UI                          |
| Latency Heatmap (per-stage)                 | ❌ MISSING | `metrics.py` có `record_latency()` nhưng không có heatmap visualization                       |
| Order Lifecycle Trace                       | ❌ MISSING | Không có trace per order_id xuyên suốt pipeline                                               |
| Exchange Health Status                      | ❌ MISSING | Không có exchange connectivity health check                                                   |
| Real-time Alerts (Telegram/Email/PagerDuty) | ❌ MISSING | Không có alerting integration nào                                                             |
| OpenTelemetry Tracing                       | ❌ MISSING | `opentelemetry-api` trong `pyproject.toml` nhưng **không có 1 trace span nào được implement** |

#### 🔥 CRITICAL VIOLATION

`warroom_service.py` line 90: `await asyncio.sleep(self.update_interval_s)` — **Vi phạm Zero Latency Rule**. Dashboard broadcast phải driven bằng event (metric update event), không phải time-based sleep.

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `monitoring/trace_manager.py` — OpenTelemetry span manager: `trace_order(order_id)`, `end_span(span_id, status)`
- **[MODIFY]** `monitoring/warroom_service.py` — Thay `asyncio.sleep` bằng event-driven broadcast, thêm exchange health probe
- **[NEW]** `monitoring/alerting.py` — Alert router: Telegram + Email, severity-based routing
- **[NEW]** `monitoring/latency_heatmap.py` — Per-stage latency tracking with percentile aggregation (p50/p95/p99)

---

### 2.14 SECURITY & AUDIT — §5.3

#### Files liên quan

- `qtrader/security/rbac.py` (45 lines — enum only)
- `qtrader/security/key_rotation.py` (2.4KB)
- `qtrader/api/` (chưa scan sâu)

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §5.3)                                | Trạng thái  | Chi tiết                                                                                                   |
| ------------------------------------------------------ | ----------- | ---------------------------------------------------------------------------------------------------------- |
| API Key Encryption                                     | ⚠️ PARTIAL  | `key_rotation.py` tồn tại                                                                                  |
| RBAC Enforcement                                       | 🔥 CRITICAL | `rbac.py` chỉ có enum + `has_permission()` function — **không có middleware**, không integrate với FastAPI |
| Secret Rotation (Auto)                                 | ⚠️ PARTIAL  | `key_rotation.py` có logic nhưng không có scheduler                                                        |
| Network Isolation (VPC)                                | ❌ MISSING  | Không có VPC/network isolation config trong Docker                                                         |
| Order Signing & Verification                           | ❌ MISSING  | Không có HMAC/signature cho orders trước khi gửi exchange                                                  |
| Audit Trail (5-10 năm retention)                       | ❌ MISSING  | Logs dùng `loguru` nhưng không có structured audit store                                                   |
| Human Override must have MFA + Reason Log              | ❌ MISSING  | Không có override governance flow                                                                          |
| Trade Surveillance (Wash trading / Spoofing detection) | ❌ MISSING  | HFT spoofing detector phát hiện spoofing từ ngoài nhưng không self-surveillance                            |

#### Kỹ thuật yêu cầu để nâng cấp

- **[NEW]** `security/middleware.py` — FastAPI dependency: `require_permission(Permission.EXECUTE)`, extract JWT, validate RBAC
- **[NEW]** `security/audit_store.py` — Append-only DuckDB table: `(timestamp, user_id, action, reason, ip_address, signature)`
- **[NEW]** `security/order_signer.py` — HMAC-SHA256 order signing before sending to exchange
- **[MODIFY]** `security/key_rotation.py` — Thêm scheduler trigger via event, không dùng cron/sleep

---

### 2.15 HA & RELIABILITY — §5.2

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §5.2)                    | Trạng thái      | Chi tiết                       |
| ------------------------------------------ | --------------- | ------------------------------ |
| Uptime ≥ 99.9%                             | ❌ NOT VERIFIED | Không có SLA monitoring        |
| Active/Active hoặc Active/Passive Failover | ❌ MISSING      | Single-node Docker deployment  |
| Stateful OMS Replication (multi-node)      | ❌ MISSING      | StateStore dùng in-memory dict |
| Failover < 5 seconds (no double execution) | ❌ MISSING      | Không có failover test         |
| HA Failover Test in Production Checklist   | ❌ MISSING      | Production checklist chưa pass |

---

### 2.16 TCA (TRANSACTION COST ANALYSIS) — §9

#### Trạng thái từng yêu cầu

| Yêu cầu (standash §9)                                  | Trạng thái | Chi tiết                                                                                 |
| ------------------------------------------------------ | ---------- | ---------------------------------------------------------------------------------------- |
| Implementation Shortfall measurement                   | ❌ MISSING | `execution/execution_quality.py` (5.7KB) có một số metrics nhưng không có IS calculation |
| Slippage Decomposition (Timing / Market Impact / Fees) | ⚠️ PARTIAL | `execution/slippage_model.py` (5.5KB) — model tồn tại nhưng decomposition chưa đầy đủ    |
| Venue Ranking by Fill Quality                          | ❌ MISSING | Không có per-exchange performance ranking                                                |

---

## 3. BỘ VẤN ĐỀ TRÙNG LẶP / DƯ THỪA CẦN DỌN DẸP

| File 1                                | File 2                                          | Vấn đề                     | Hành động                                         |
| ------------------------------------- | ----------------------------------------------- | -------------------------- | ------------------------------------------------- |
| `execution/shadow.py` (30 lines)      | `execution/shadow_engine.py` (12.6KB)           | Hai shadow implementations | **DELETE** `shadow.py`                            |
| `execution/microprice.py`             | `hft/microprice.py`                             | Hai microprice modules     | **DELETE** `execution/microprice.py`, dùng `hft/` |
| `execution/sor.py`                    | `execution/sor_microprice.py`                   | Hai SOR files cùng size    | **MERGE** vào `execution/sor.py`                  |
| `execution/algos.py`                  | `execution/algos/` (dir)                        | File và directory cùng tên | **DELETE** `algos.py`, dùng `algos/` directory    |
| `qtrader/risk/portfolio_allocator.py` | `qtrader/portfolio/allocator.py`                | Allocator trong 2 modules  | **MOVE** tất cả vào `portfolio/`                  |
| `core/logger.py`                      | `core/logging.py`                               | Hai logging files          | **MERGE** vào `core/logging.py`                   |
| `qtrader/oms/interface.py`            | `execution/oms.py` + `execution/oms_adapter.py` | OMS bị phân tán            | **CONSOLIDATE** vào `qtrader/oms/`                |

---

## 4. VI PHẠM CORE PRINCIPLES (KHÔNG ĐƯỢC VI PHẠM)

### 🔥 Zero Latency Rule Violations

| File                            | Dòng | Vi phạm                                       | Mức độ   |
| ------------------------------- | ---- | --------------------------------------------- | -------- |
| `core/orchestrator.py`          | 714  | `await asyncio.sleep(0.01)` trong main loop   | CRITICAL |
| `monitoring/warroom_service.py` | 90   | `await asyncio.sleep(self.update_interval_s)` | HIGH     |
| Tiềm năng: `hft/optimizer.py`   | TBD  | Cần scan để tìm thêm                          | MEDIUM   |

**Fix bắt buộc:** Tất cả timing phải event-driven. Main orchestrator loop phải `await event_bus.next_event()`.

### 🔥 No Silent Failure Violations

| File                                 | Vấn đề                                                                       |
| ------------------------------------ | ---------------------------------------------------------------------------- |
| `execution/reconciliation_engine.py` | Trả về `"MISMATCH"` string nhưng **không publish event, không halt trading** |
| `execution/shadow.py`                | `# Logic to calculate shadow fills and pnl...` — **silent no-op stub**       |
| `monitoring/warroom_service.py`      | Dùng `print()` thay vì `loguru`, không có Trace ID                           |

### 🔥 Stateless Strategy Design Violation

| Vấn đề                                                                                                            | File                                |
| ----------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| `TradingOrchestrator` giữ `self.last_approved_allocation` và `self.last_approved_risk_metrics` như instance state | `core/orchestrator.py` line 305-306 |
| State này mất khi crash, không được persist vào StateStore                                                        | Cần move sang `StateStore`          |

---

## 5. PRODUCTION READINESS CHECKLIST (HIỆN TẠI)

| Hạng mục (từ standash §12)              | Trạng thái                                     |
| --------------------------------------- | ---------------------------------------------- |
| Real-time Recon Verified (fill-by-fill) | ❌ FAIL — không có auto-halt                   |
| Clock Sync Sync (PTP/NTP)               | ❌ FAIL — không tồn tại                        |
| TCA Baseline                            | ❌ FAIL — không có TCA module                  |
| HA Failover Test                        | ❌ FAIL — single-node only                     |
| FSM Validation (stress test)            | ⚠️ PARTIAL — FSM có nhưng không có stress test |

> **KẾT LUẬN: HỆ THỐNG CHƯA ĐẠT PRODUCTION READINESS. Tất cả 5 hạng mục checklist đều FAIL hoặc PARTIAL.**

---

## 6. UPGRADE ROADMAP — THỨ TỰ ƯU TIÊN

### Phase 1 — Critical Fixes (Unblocking Production)

> **Mục tiêu:** Eliminate all CRITICAL violations. Không launch live trading khi chưa xong Phase 1.

| Ưu tiên | Task                                                                | Module                                | Effort |
| ------- | ------------------------------------------------------------------- | ------------------------------------- | ------ |
| P0      | Implement `oms/order_management_system.py` (full OMS impl)          | `qtrader/oms/`                        | High   |
| P0      | `reconciliation_engine.py` → auto-halt on mismatch                  | `qtrader/execution/`                  | Medium |
| P0      | Fix `asyncio.sleep()` violations → event-driven                     | `core/orchestrator.py`, `monitoring/` | Medium |
| P0      | Delete stub `shadow.py`, implement Shadow PnL in `shadow_engine.py` | `qtrader/execution/`                  | Medium |
| P0      | RBAC middleware enforcement in FastAPI                              | `qtrader/security/`                   | Medium |

### Phase 2 — Core Infrastructure Gaps

> **Mục tiêu:** Fill all ❌ MISSING items that block institutional operation.

| Ưu tiên | Task                                      | Module                | Effort |
| ------- | ----------------------------------------- | --------------------- | ------ |
| P1      | Feed Arbitrator (A/B feeds) + Clock Sync  | `qtrader/data/`       | High   |
| P1      | Event Sourcing + Replay Engine            | `qtrader/oms/`        | High   |
| P1      | NAV Engine + Cash Ledger                  | `qtrader/portfolio/`  | Medium |
| P1      | OpenTelemetry trace spans across pipeline | `qtrader/monitoring/` | Medium |
| P1      | Feature Flags hot-reload                  | `qtrader/core/`       | Low    |
| P1      | War Mode FSM                              | `qtrader/risk/`       | Medium |

### Phase 3 — Institutional-Grade Hardening

> **Mục tiêu:** Reach Tier-1 Hedge Fund Grade standard.

| Ưu tiên | Task                                                       | Module               | Effort    |
| ------- | ---------------------------------------------------------- | -------------------- | --------- |
| P2      | HA Failover (Active/Passive) + OMS Replication             | Infrastructure       | Very High |
| P2      | Full TCA Engine (Implementation Shortfall + Venue Ranking) | `qtrader/analytics/` | High      |
| P2      | Audit Trail (5-year retention, structured)                 | `qtrader/security/`  | Medium    |
| P2      | Quote Stuffing Detector                                    | `qtrader/hft/`       | Medium    |
| P2      | Strategy Lifecycle FSM + Committee Review Gate             | `qtrader/strategy/`  | High      |
| P2      | Codebase Deduplication (7 pairs identified in §3)          | Entire codebase      | Medium    |
| P2      | Test coverage audit (target >90%)                          | `tests/`             | High      |

---

## 7. TECHNICAL DEBT INVENTORY

| Loại debt                        | Số lượng | Ví dụ                                                                                              |
| -------------------------------- | -------- | -------------------------------------------------------------------------------------------------- |
| Stub/Empty implementations       | 4+       | `shadow.py`, `oms/interface.py`, `portfolio/optimizer.py` (737 bytes)                              |
| TODO comments in production code | 3+       | `orchestrator.py` lines 87, 263, 397                                                               |
| Magic numbers hardcoded          | 3+       | `max_drawdown = 0.20`, `max_var = 0.05`, `max_leverage = 5.0` trong orchestrator (không từ config) |
| `print()` thay vì loguru         | 1+       | `warroom_service.py`                                                                               |
| Missing `__init__.py`            | 1+       | `qtrader/hft/`                                                                                     |
| Duplicate files                  | 7 pairs  | Xem §3                                                                                             |
| asyncio.sleep violations         | 2        | Xem §4                                                                                             |

---

## 8. ĐỊNH NGHĨA "DONE" CHO HỆ THỐNG

Hệ thống được coi là **Tier-1 Hedge Fund Grade** khi tất cả điều kiện sau được đáp ứng:

```bash
# DoD Command (must all pass)
ruff check qtrader/ tests/ \
  && mypy qtrader/ --strict \
  && pytest tests/ --cov=qtrader --cov-fail-under=90 \
  && cd rust_core && cargo test

# Plus production checklist:
# ✅ Real-time reconciliation with auto-halt verified
# ✅ Clock sync drift < 1ms verified
# ✅ Shadow mode run ≥ 7 days with PnL within tolerance
# ✅ HA failover test < 5s with zero double-execution
# ✅ FSM stress test: 10,000 order state transitions with 0 invalid transitions
# ✅ Zero asyncio.sleep() in production code paths
# ✅ All CRITICAL gaps in this document resolved
```

---

_Tài liệu này được tạo bởi deep scan tự động ngày 2026-03-25. Cập nhật định kỳ sau mỗi sprint. Tham chiếu chuẩn: [standash-document.md](./standash-document.md)_
