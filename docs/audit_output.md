# QTRADER — SYSTEM GAP ANALYSIS & UPGRADE BLUEPRINT v2.0

> **Ngày phân tích:** 2026-03-25  
> **Phiên bản hệ thống:** v0.1.0-pre-alpha  
> **Phương pháp:** Deep scan 180+ source files, 93 test files, 6 Rust modules  
> **Tham chiếu chuẩn:** [`standash-document.md`](./standash-document.md) (Tier-1 Institutional Hedge Fund Grade)

---

## LEGEND

| Ký hiệu          | Ý nghĩa                                          |
| ---------------- | ------------------------------------------------ |
| ✅ **DONE**      | Đã triển khai đầy đủ, đạt chuẩn                  |
| ⚠️ **PARTIAL**   | Có code nhưng chưa hoàn thiện hoặc chưa tích hợp |
| ❌ **MISSING**   | Chưa tồn tại hoặc chỉ là stub rỗng               |
| 🔥 **CRITICAL**  | Lỗi nghiêm trọng vi phạm Core Principles         |
| 🗑️ **REDUNDANT** | File/module trùng lặp gây confusion              |

---

## 1. EXECUTIVE SUMMARY

> **GRADE: Pre-Alpha Production — NOT READY FOR LIVE TRADING**

### Thống kê tổng quan

| Metric                             | Số lượng                                                                                                                                                                                                                                                                             |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Tổng source files                  | **180+**                                                                                                                                                                                                                                                                             |
| Tổng test files                    | **93**                                                                                                                                                                                                                                                                               |
| Submodules                         | **25** (`alpha/`, `analytics/`, `api/`, `backtest/`, `bot/`, `core/`, `data/`, `execution/`, `features/`, `feedback/`, `hft/`, `meta/`, `ml/`, `models/`, `monitoring/`, `oms/`, `pipeline/`, `portfolio/`, `research/`, `risk/`, `security/`, `strategy/`, `utils/`, `validation/`) |
| Rust core modules                  | **6** (`algo.rs`, `lib.rs`, `matching.rs`, `oms.rs`, `risk.rs`, `simulator.rs`)                                                                                                                                                                                                      |
| `asyncio.sleep` violations         | **38** (across 20 files)                                                                                                                                                                                                                                                             |
| `time.sleep` violations            | **2**                                                                                                                                                                                                                                                                                |
| Files dùng `print()` thay `loguru` | **11**                                                                                                                                                                                                                                                                               |
| Missing `__init__.py`              | **11** packages                                                                                                                                                                                                                                                                      |
| Duplicate file pairs               | **7**                                                                                                                                                                                                                                                                                |
| TODO comments in prod code         | **3**                                                                                                                                                                                                                                                                                |

### Top 12 điểm yếu nghiêm trọng nhất

| #   | Khu vực             | Mức độ       | Vấn đề cốt lõi                                                                     |
| --- | ------------------- | ------------ | ---------------------------------------------------------------------------------- |
| 1   | Zero-Latency        | 🔥 CRITICAL  | **38 `asyncio.sleep` violations** trải rộng 20 files — vi phạm Core Principle §2.4 |
| 2   | Reconciliation      | 🔥 CRITICAL  | `reconciliation_engine.py` (51 dòng) — không trigger Trading Halt khi mismatch     |
| 3   | Shadow Mode         | 🔥 CRITICAL  | `shadow.py` là stub 30 dòng — không tính PnL, không so sánh backtest vs live       |
| 4   | RBAC/Security       | 🔥 CRITICAL  | `security/rbac.py` là 45-dòng enum — không có middleware enforcement               |
| 5   | Feed Arbitration    | ❌ MISSING   | Không có A/B Feed Arbitrator, không clock sync PTP/NTP                             |
| 6   | Monitoring/War Room | ❌ MISSING   | Không có Latency Heatmap, Order Lifecycle Trace, Alerting                          |
| 7   | HA/Failover         | ❌ MISSING   | Single-node Docker, không Active/Passive, không stateful replication               |
| 8   | Capital Accounting  | ❌ MISSING   | Không NAV real-time, không Cash Ledger, không Funding tracking                     |
| 9   | TCA Engine          | ❌ MISSING   | Không Implementation Shortfall, không Venue Ranking                                |
| 10  | Dynamic Config      | ❌ MISSING   | Config là static YAML — không có Feature Flags, không hot-reload                   |
| 11  | Code Duplication    | 🗑️ REDUNDANT | 7 cặp file trùng lặp gây confusion và tốn bảo trì                                  |
| 12  | Missing Packages    | ⚠️ PARTIAL   | 11 submodules thiếu `__init__.py` — import sẽ fail trong production                |

---

## 2. PHÂN TÍCH CHI TIẾT THEO LAYER

---

### 2.1 MARKET DATA LAYER (L3 STANDARD) — standash §4.1

**Files:** `data/quality_gate.py` (165L), `data/quality.py` (88L), `data/market/market_feed.py` (62L), `data/market/ohlcv.py` (40L), `data/market/coinbase_market.py`, `data/pipeline/sources/coinbase.py` (99L), `data/pipeline/sources/csv_source.py` (32L)

| Yêu cầu                             | Status     | Chi tiết                                                                             |
| ----------------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| Feed Arbitration (A/B feeds)        | ❌ MISSING | Không có `feed_arbitrator.py` trong toàn bộ codebase                                 |
| Sequence ID Gap Detection < 1ms     | ⚠️ PARTIAL | `check_sequence_gap()` có trong `quality_gate.py` nhưng không tích hợp live pipeline |
| Orderbook Snapshot L2/L3 Recovery   | ⚠️ PARTIAL | `orderbook_enhanced.py` (437L) tồn tại nhưng không có snapshot recovery flow         |
| Timestamp Alignment / Normalization | ❌ MISSING | Không có Clock Sync module, không PTP/NTP adapter                                    |
| Outlier Detection (Z-score/MAD)     | ⚠️ PARTIAL | Z-score có, **MAD chưa có**                                                          |
| Stale Data Detection                | ✅ DONE    | `check_stale()` trong `quality_gate.py`                                              |
| Cross-exchange Price Sanity         | ✅ DONE    | `check_cross_exchange_sanity()`                                                      |
| Trade/Quote Mismatch Check          | ❌ MISSING | Không có logic kiểm tra order vs fill logic consistency                              |

**🔥 Zero-Latency Violations trong Data Layer:**

- `data/market/market_feed.py:62` — `await asyncio.sleep(self.interval_sec)`
- `data/pipeline/sources/coinbase.py:60,64` — `await asyncio.sleep(1.0)` (2 chỗ)
- `data/market/coinbase_market.py:129,133` — **`time.sleep(0.15)`, `time.sleep(1.0)`** — blocking call trong data pipeline!

**Upgrade Tasks:**

- **[NEW]** `data/feed_arbitrator.py` — A/B feed arbitration, sequence gap detect < 1ms, publish to EventBus
- **[NEW]** `data/clock_sync.py` — NTP/PTP adapter, expose `get_exchange_aligned_timestamp(exchange_id) -> datetime`
- **[MODIFY]** `quality_gate.py` — Thêm `check_outlier(method="mad")`, `check_trade_quote_mismatch()`
- **[FIX]** `coinbase_market.py` — Replace `time.sleep()` with event-driven approach

---

### 2.2 ALPHA ENGINE / FEATURE FACTORY — standash §4.2 & §4.3

**Files:** `alpha/` — 16 files (base, combiner, decay, ensemble_model, factor_model, factory, ic, registry, meta_learning, meta_selector, microstructure, signal_model, technical, feature_importance, feature_selection) + `alpha/models/gbdt_model.py`. `features/` — store.py (282L), registry.py (169L), base.py (155L), engine.py (68L), neutralization.py (231L), 5 subdirs.

| Yêu cầu                             | Status     | Chi tiết                                                                               |
| ----------------------------------- | ---------- | -------------------------------------------------------------------------------------- |
| 100% Vectorized (Polars/NumPy)      | ✅ DONE    | Codebase dùng Polars expressions                                                       |
| No Python loops (iloc in loops)     | ✅ DONE    | Không thấy `df.iloc` trong loops                                                       |
| Point-in-Time Integrity             | ⚠️ PARTIAL | Tests yêu cầu look-ahead bias check nhưng **coverage chưa đo được**                    |
| IC > 0.02 validation                | ✅ DONE    | `alpha/ic.py` có IC computation                                                        |
| IC Decay Analysis                   | ✅ DONE    | `alpha/decay.py`                                                                       |
| Feature Drift Auto-Disable (PSI/KS) | ⚠️ PARTIAL | `analytics/drift_detector.py` tồn tại nhưng **chỉ log warning, không disable feature** |
| Dataset Versioning                  | ✅ DONE    | `data/versioning.py` (93L)                                                             |
| Feature Lineage                     | ✅ DONE    | `data/lineage.py`                                                                      |

**Upgrade Tasks:**

- **[MODIFY]** `alpha/factory.py` — Khi `drift_detector` phát hiện PSI > 15%, gọi `registry.disable_feature(name)` thay vì chỉ log
- **[NEW]** `features/pit_validator.py` — Point-in-Time guard: validate `df[i]` không dùng data từ `df[i+1:]`
- **[NEW]** `alpha/models/__init__.py` — Missing init file

---

### 2.3 STRATEGY ENGINE — standash §4.4

**Files:** `strategy/` — 16 files (probabilistic_strategy.py 231L, ensemble_strategy.py 337L, regime_meta_strategy.py 149L, momentum.py 143L, mean_reversion.py 131L, base.py 242L, strategy_layer.py 175L, meta_strategy.py 177L, alpha_combiner.py 121L, alpha_base.py 127L, alpha/candle_patterns_alpha.py 403L, validation/feature_validator.py 66L)

| Yêu cầu                                              | Status     | Chi tiết                                                                               |
| ---------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------- |
| Probabilistic Output (BUY/SELL/HOLD với probability) | ✅ DONE    | `probabilistic_strategy.py` (231L)                                                     |
| Ensemble Dynamic Weighting (24h/7d)                  | ⚠️ PARTIAL | `ensemble_strategy.py` — weight update dựa trên hardcoded regime, không rolling window |
| Strategy Sandbox Isolation                           | ❌ MISSING | Không process isolation, không per-strategy capital limits                             |
| Strategy Lifecycle (Research→Paper→Shadow→Live)      | ⚠️ PARTIAL | Không approval gate, shadow mode là stub                                               |
| Kill Model without Kill System                       | ⚠️ PARTIAL | `NetworkKillSwitch` kill toàn bộ system, không có model-level kill                     |

**Upgrade Tasks:**

- **[NEW]** `strategy/sandbox.py` — StrategySandbox: isolated capital counter + circuit breaker per strategy
- **[NEW]** `strategy/lifecycle.py` — State machine: `RESEARCH` → `PAPER` → `SHADOW` → `COMMITTEE_REVIEW` → `LIVE` → `SUSPENDED`
- **[MODIFY]** `strategy/ensemble_strategy.py` — Weight update dùng rolling performance window (24h/7d)
- **[MODIFY]** `risk/network_kill_switch.py` — Thêm `kill_strategy(strategy_id)`
- **[NEW]** `strategy/__init__.py` (nếu missing), `strategy/alpha/__init__.py`, `strategy/validation/__init__.py`

---

### 2.4 PORTFOLIO ALLOCATOR — standash §4.5

**Files:** `portfolio/` — 14 files (accounting.py 268L, allocator.py 227L, capital_allocator.py 117L, factor_neutral.py 88L, fees.py 238L, hrp.py 233L, kelly.py 148L, multi_asset_engine.py 357L, optimization.py 63L, optimizer.py 31L, position_sizing.py 34L, risk_parity.py 137L, sizing.py 113L)

| Yêu cầu                            | Status     | Chi tiết                                                                            |
| ---------------------------------- | ---------- | ----------------------------------------------------------------------------------- |
| Risk Parity thực thụ               | ✅ DONE    | `portfolio/risk_parity.py` (137L)                                                   |
| Correlation-aware Allocation (HRP) | ✅ DONE    | `hrp.py` (233L)                                                                     |
| Volatility Targeting               | ⚠️ PARTIAL | `risk/volatility.py`, `portfolio/sizing.py` tồn tại nhưng tích hợp pipeline chưa rõ |
| Factor Neutralization              | ✅ DONE    | `portfolio/factor_neutral.py`, `features/neutralization.py`                         |
| Exposure Decomposition             | ⚠️ PARTIAL | `risk/exposure.py` (91L), `risk/factor_risk.py` (145L) — chưa verified output       |
| QP/Convex Optimization             | ⚠️ PARTIAL | `portfolio/optimization.py` (63L — rất mỏng), `optimizer.py` (31L — gần rỗng)       |

**🗑️ Redundancy:** `risk/portfolio_allocator_enhanced.py` (455L) vs `portfolio/allocator.py` (227L) — allocator logic phân tán giữa `risk/` và `portfolio/`

**Upgrade Tasks:**

- **[MODIFY]** `portfolio/optimization.py` — Triển khai QP solver đầy đủ dùng `scipy.optimize.minimize` với constraint matrix
- **[DELETE]** `portfolio/optimizer.py` (31L stub) — merge với `optimization.py`
- **[MOVE]** `risk/portfolio_allocator_enhanced.py` → consolidate vào `portfolio/`
- **[NEW]** `portfolio/exposure_pipeline.py` — Kết nối `factor_risk.py` → `allocator.py` → output factor-decomposed risk report

---

### 2.5 RISK ENGINE (CRITICAL CORE) — standash §4.6

**Files:** `risk/` — 15 files (runtime_risk_engine.py 563L, limits.py 291L, realtime.py 277L, runtime.py 232L, feature_validation.py 226L, network_kill_switch.py 209L, portfolio_allocator_enhanced.py 455L, factor_risk.py 145L, attribution.py 164L, drawdown_control.py 95L, exposure.py 91L, regime_adapter.py 88L, volatility.py 79L, position_sizer.py 65L, base.py 20L)

| Yêu cầu                                 | Status     | Chi tiết                                                                          |
| --------------------------------------- | ---------- | --------------------------------------------------------------------------------- |
| Real-time VaR, Drawdown, Leverage       | ✅ DONE    | `runtime_risk_engine.py` + `realtime.py`                                          |
| Fat-finger Protection                   | ✅ DONE    | `risk/limits.py` (291L)                                                           |
| Concentration Limit (max 5% per symbol) | ✅ DONE    | `limits.py`                                                                       |
| Kill Switch (`kill_switch()`)           | ✅ DONE    | `network_kill_switch.py` (209L)                                                   |
| Regime-aware Risk Adjustment            | ✅ DONE    | `risk/regime_adapter.py` (88L)                                                    |
| Capital Preservation / War Mode         | ❌ MISSING | Không có `WarMode` FSM — chỉ có kill switch, **không có Hedging/Unwind logic**    |
| HMM Regime → Auto Strategy Deactivation | ⚠️ PARTIAL | Logic tồn tại trong `ml/regime_detector.py` nhưng kết nối risk engine chưa đầy đủ |

**Upgrade Tasks:**

- **[NEW]** `risk/war_mode.py` — `WarMode` FSM: Trigger → Stop New Positions → Reduce Exposure 50% → Hedge Only → Full Unwind
- **[MODIFY]** `risk/regime_adapter.py` — Kết nối auto-deactivate strategies trong extreme regime

---

### 2.6 EXECUTION ENGINE — standash §4.7

**Files:** `execution/` — 31 files (execution_engine.py 605L, orderbook_enhanced.py 437L, shadow_engine.py 295L, smart_router.py 304L, oms_adapter.py 285L, reconciliation_service.py 252L, orderbook_simulator.py 225L, sor.py 194L, rl_agent.py 186L, benchmark_orderbook.py 180L, paper_engine.py 170L, execution_quality.py 153L, order_fsm.py 142L, slippage_model.py 127L, multi_exchange_adapter.py 198L, brokers/coinbase.py 286L, brokers/binance.py 142L, exchange/binance_adapter.py 239L, exchange/coinbase_adapter.py 172L, algos/twap.py 91L, algos/vwap.py 84L, algos/pov.py 64L, etc.)

| Yêu cầu                      | Status     | Chi tiết                                                      |
| ---------------------------- | ---------- | ------------------------------------------------------------- |
| Async non-blocking           | ✅ DONE    | Toàn bộ execution dùng `async/await`                          |
| Global Unique Order ID       | ✅ DONE    | `execution/order_id.py` (103L)                                |
| Idempotent Order ID          | ✅ DONE    | `order_id.py`                                                 |
| Queue Position Modeling      | ✅ DONE    | `hft/queue_model.py` (79L)                                    |
| Hidden Liquidity Detection   | ⚠️ PARTIAL | Chưa có explicit hidden liquidity model                       |
| Adverse Selection Modeling   | ✅ DONE    | `execution/adverse_model.py` (75L), `hft/toxic_flow.py` (81L) |
| Toxic Flow Detection         | ✅ DONE    | `hft/toxic_flow.py`                                           |
| Orderbook Spoofing Detection | ✅ DONE    | `hft/spoofing.py` (82L)                                       |
| Quote Stuffing Detection     | ❌ MISSING | Không có explicit quote stuffing detector                     |

**🔥 MASSIVE Zero-Latency Violations in Execution (10 files, 16 locations):**

| File                          | Line         | Vi phạm                                                                              |
| ----------------------------- | ------------ | ------------------------------------------------------------------------------------ |
| `execution_engine.py`         | 383, 395     | `await asyncio.sleep(delay)` trong retry logic                                       |
| `execution_engine.py`         | 492          | `await asyncio.sleep(0.1)` — poll loop                                               |
| `execution_engine.py`         | 504, 528     | `await asyncio.sleep(1.0)` — error backoff                                           |
| `reconciliation_service.py`   | 85, 90       | `await asyncio.sleep(self.reconciliation_interval)`                                  |
| `latency_model.py`            | 49           | `await asyncio.sleep(total_latency_ms / 1000.0)` — **artificial latency injection!** |
| `adapters/binance_adapter.py` | 54, 88       | `await asyncio.sleep(0.01)`                                                          |
| `exchange/binance_adapter.py` | 61, 132, 166 | `await asyncio.sleep(...)` — rate limit và mock                                      |
| `brokers/coinbase.py`         | 99           | `await asyncio.sleep(0.1)` — "Simulated network latency"                             |
| `http.py`                     | 74           | `await asyncio.sleep(sleep_s)` — retry backoff                                       |

---

### 2.7 SMART ORDER ROUTER (SOR) — standash §4.8

**Files:** `execution/sor.py` (194L), `execution/smart_router.py` (304L), `hft/microprice.py` (72L), `hft/imbalance.py` (115L)

| Yêu cầu                                  | Status     | Chi tiết                                                    |
| ---------------------------------------- | ---------- | ----------------------------------------------------------- |
| Micro-price Logic + Orderbook Imbalance  | ✅ DONE    | `hft/microprice.py` + `hft/imbalance.py` — fully vectorized |
| Liquidity Sweeping (split across venues) | ⚠️ PARTIAL | `smart_router.py` (304L) — chưa rõ multi-venue sweep logic  |

**🗑️ Redundancy Issues:**

- `execution/sor.py` vs `execution/sor_microprice.py` (nếu tồn tại) — cùng logic
- `execution/microprice.py` vs `hft/microprice.py` — hai module microprice

**Upgrade Tasks:**

- **[MERGE/DELETE]** Consolidate SOR files vào `execution/sor.py` duy nhất
- **[DELETE]** `execution/microprice.py` — dùng `hft/microprice.py` làm single source
- **[MODIFY]** `smart_router.py` — Thêm explicit multi-venue order splitting với liquidity weighting

---

### 2.8 OMS & POSITION RECONCILIATION — standash §4.9

**Files:** `oms/interface.py` (65L — abstract class), `oms/order_management_system.py` (228L — **FULL IMPLEMENTATION**), `oms/oms_adapter.py` (285L), `oms/oms_multi_adapter.py` (213L), `execution/reconciliation_engine.py` (50L), `execution/reconciliation_service.py` (252L), `execution/order_fsm.py` (142L)

| Yêu cầu                                        | Status      | Chi tiết                                                                                                                                                            |
| ---------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OMS Implementation                             | ✅ DONE     | `oms/order_management_system.py` (228L) — `UnifiedOMS` + `PositionManager` + `Position` dataclass. **FIFO position tracking, P&L computation, multi-venue routing** |
| FSM States (NEW→ACK→FILLED→CANCELLED→REJECTED) | ✅ DONE     | `execution/order_fsm.py` (142L)                                                                                                                                     |
| Idempotent State Transitions                   | ✅ DONE     | `order_fsm.py`                                                                                                                                                      |
| Pending Timeout + Auto-Reconcile               | ⚠️ PARTIAL  | Timeout handling chưa rõ                                                                                                                                            |
| Real-time Reconciliation (per-Fill)            | ⚠️ PARTIAL  | `reconciliation_engine.py` (50L) chỉ compare dicts — **không trigger halt**                                                                                         |
| Periodic Reconciliation (1m)                   | ⚠️ PARTIAL  | `reconciliation_service.py` (252L) — chưa verify integration                                                                                                        |
| Hard Mismatch → Trading Halt                   | 🔥 CRITICAL | `reconciliation_engine.py` trả về `"MISMATCH"` — **không trigger Trading Halt event**                                                                               |
| Event Sourcing & Full Replay Engine            | ❌ MISSING  | Không có Event Log store, không có Replay engine                                                                                                                    |
| Stateful OMS Replication                       | ❌ MISSING  | `UnifiedOMS` dùng in-memory dict, không persistence                                                                                                                 |

> [!IMPORTANT]
> **Corrected Assessment**: `oms/order_management_system.py` đã có 228-dòng implementation đầy đủ (`UnifiedOMS`, `PositionManager` với FIFO tracking, realized/unrealized PnL). Đây không phải stub — nhưng thiếu persistence, event sourcing, và reconciliation auto-halt.

**Upgrade Tasks:**

- **[MODIFY]** `reconciliation_engine.py` — Thêm `EventType.TRADING_HALT` publish khi mismatch
- **[NEW]** `oms/event_store.py` — Append-only event log (DuckDB): persist mọi order+fill events
- **[NEW]** `oms/replay_engine.py` — Rebuild OMS state từ event log
- **[MODIFY]** `execution/order_fsm.py` — Thêm timeout per state, trigger `auto_reconcile()`
- **[NEW]** `oms/__init__.py` — Missing package init

---

### 2.9 HFT & CLOCK INFRASTRUCTURE — standash §4.10

**Files:** `hft/` — 8 files (optimizer.py 475L, rl_agent.py 154L, market_maker.py 88L, queue_model.py 79L, microprice.py 72L, imbalance.py 115L, toxic_flow.py 81L, spoofing.py 82L)

| Yêu cầu                               | Status     | Chi tiết                                                  |
| ------------------------------------- | ---------- | --------------------------------------------------------- |
| Clock Synchronization (PTP/NTP)       | ❌ MISSING | Orchestrator dùng `datetime.utcnow()` không sync          |
| Timestamp Normalization (drift < 1ms) | ❌ MISSING | Không drift detection                                     |
| CPU Core Isolation / Pinning          | ❌ MISSING | Không CPU affinity configuration                          |
| HFT Optimizer                         | ✅ DONE    | `hft/optimizer.py` (475L) — adaptive latency, safety mode |
| Market Maker Logic                    | ✅ DONE    | `hft/market_maker.py`                                     |
| Self-healing Auto-restart             | ⚠️ PARTIAL | Docker `restart: always` nhưng không Gradual Recovery     |
| Gradual Recovery                      | ❌ MISSING | All-or-nothing restart                                    |

**❌ Missing:** `hft/__init__.py` — package init file not present

**Upgrade Tasks:**

- **[NEW]** `data/clock_sync.py` — NTP polling + monotonic clock correction
- **[NEW]** `core/health_manager.py` — Component health registry, gradual restart
- **[NEW]** `hft/__init__.py`

---

### 2.10 MLOPS & SHADOW MODE — standash §4.11 & §4.13

**Files:** `ml/` — 16 files (mlflow_manager.py 669L, regime_detector.py 465L, regime.py 337L, evaluation.py 338L, meta_learning_engine.py 301L, meta_online.py 273L, pytorch_models.py 211L, hmm_regime.py 168L, hmm_smoother.py 153L, walk_forward.py 152L, stability.py 147L, autonomous.py 142L, registry.py 131L, online_learning.py 124L, distributed.py 171L, rotation.py 33L)

`execution/shadow_engine.py` (295L)

| Yêu cầu                                       | Status      | Chi tiết                                                      |
| --------------------------------------------- | ----------- | ------------------------------------------------------------- |
| MLflow Model Versioning + Experiment Tracking | ✅ DONE     | `ml/mlflow_manager.py` (669L) — rất đầy đủ                    |
| Shadow Mode ≥ 7 ngày bắt buộc                 | ❌ MISSING  | Không minimum duration enforcement                            |
| Shadow PnL Calculation                        | 🔥 CRITICAL | `shadow.py` có comment placeholder — **chưa có code thực**    |
| Shadow vs Live Comparison (daily)             | ❌ MISSING  | Không daily comparison job                                    |
| Drift Auto-Retrain                            | ⚠️ PARTIAL  | DriftDetector log warning nhưng không trigger retrain tự động |

**🔥 `asyncio.sleep` trong `ml/autonomous.py:122`** — `await asyncio.sleep(self.interval_s)` trong autonomous learning loop

**Upgrade Tasks:**

- **[DELETE]** `execution/shadow.py` (stub 30L) — dùng `shadow_engine.py` làm single source
- **[MODIFY]** `shadow_engine.py` — Thêm minimum 7-day enforcement, daily PnL comparison
- **[NEW]** `ml/retrain_scheduler.py` — Event-driven retrain khi drift > threshold

---

### 2.11 CAPITAL ACCOUNTING — standash §4.14

**Files:** `portfolio/accounting.py` (268L), `portfolio/fees.py` (238L)

| Yêu cầu                                  | Status     | Chi tiết                                                                          |
| ---------------------------------------- | ---------- | --------------------------------------------------------------------------------- |
| PnL Separation (Realized/Unrealized)     | ✅ DONE    | `PositionManager` trong `oms/order_management_system.py` tách realized/unrealized |
| Funding & Borrowing Tracking             | ❌ MISSING | Không Funding Rate tracker                                                        |
| Fee Accrual (Maker/Taker + Funding Rate) | ⚠️ PARTIAL | `fees.py` (238L) nhưng Funding Rate chưa rõ                                       |
| Multi-currency Cash Ledger               | ❌ MISSING | Không Cash Ledger module                                                          |
| NAV Real-time Calculation                | ❌ MISSING | Không NAV computation engine                                                      |
| EOD Position Snapshot                    | ❌ MISSING | Không end-of-day reconciliation                                                   |

**Upgrade Tasks:**

- **[NEW]** `portfolio/cash_ledger.py` — Multi-currency ledger, FX conversion
- **[NEW]** `portfolio/nav_engine.py` — NAV = Cash + MarkToMarket(positions)
- **[MODIFY]** `portfolio/accounting.py` — Thêm funding_cost, borrowing_cost
- **[NEW]** `portfolio/eod_snapshot.py` — Event-driven EOD persist

---

### 2.12 DYNAMIC CONFIG — standash §4.15

**Files:** `core/config.py` (65L), `utils/config.py` (65L), `configs/bot_paper.yaml`, `configs/bot_prod.yaml`, `configs/execution.yaml`

| Yêu cầu                                        | Status     | Chi tiết                                     |
| ---------------------------------------------- | ---------- | -------------------------------------------- |
| Feature Flags (toggle strategy không redeploy) | ❌ MISSING | Static YAML, no runtime toggle               |
| Runtime Risk Override                          | ❌ MISSING | No hot-reload mechanism                      |
| Exchange Routing Config                        | ⚠️ PARTIAL | `configs/execution.yaml` — static            |
| Kill Switch Config (Global + Symbol)           | ⚠️ PARTIAL | NetworkKillSwitch không configurable runtime |

**🗑️ Redundancy:** `core/config.py` (65L) vs `utils/config.py` (65L) — hai config modules

**Upgrade Tasks:**

- **[NEW]** `core/feature_flags.py` — DuckDB/Redis-backed feature flag store, hot-reload
- **[MODIFY]** `core/config.py` — Thêm `watch_config()` coroutine
- **[NEW]** `api/config_api.py` — REST endpoint: `POST /config/risk/{param}`
- **[DELETE/MERGE]** `utils/config.py` → consolidate vào `core/config.py`

---

### 2.13 MONITORING & WAR ROOM — standash §5.4

**Files:** `monitoring/` — 3 files: `api.py` (70L), `metrics.py` (141L), `warroom_service.py` (108L)

| Yêu cầu                           | Status     | Chi tiết                                                                       |
| --------------------------------- | ---------- | ------------------------------------------------------------------------------ |
| Live PnL & VaR Dashboard          | ⚠️ PARTIAL | `warroom_service.py` có `get_dashboard_snapshot()` nhưng không UI              |
| Latency Heatmap (per-stage)       | ❌ MISSING | `metrics.py` có `record_latency()` nhưng không heatmap                         |
| Order Lifecycle Trace             | ❌ MISSING | Không trace per order_id xuyên pipeline                                        |
| Exchange Health Status            | ❌ MISSING | Không exchange connectivity health check                                       |
| Alerts (Telegram/Email/PagerDuty) | ❌ MISSING | Không alerting integration                                                     |
| OpenTelemetry Tracing             | ❌ MISSING | `opentelemetry-api` trong `pyproject.toml` nhưng **0 trace spans implemented** |

**🔥 Critical:** `warroom_service.py:90` — `await asyncio.sleep(self.update_interval_s)` vi phạm Zero Latency Rule

**❌ Missing:** `monitoring/__init__.py`

**Upgrade Tasks:**

- **[NEW]** `monitoring/trace_manager.py` — OpenTelemetry span manager
- **[MODIFY]** `monitoring/warroom_service.py` — Event-driven broadcast, exchange health probe
- **[NEW]** `monitoring/alerting.py` — Telegram + Email routing
- **[NEW]** `monitoring/latency_heatmap.py` — Per-stage latency p50/p95/p99
- **[NEW]** `monitoring/__init__.py`

---

### 2.14 SECURITY & AUDIT — standash §5.3

**Files:** `security/key_rotation.py` (90L), `security/rbac.py` (44L)

| Yêu cầu                 | Status      | Chi tiết                                                                  |
| ----------------------- | ----------- | ------------------------------------------------------------------------- |
| API Key Encryption      | ⚠️ PARTIAL  | `key_rotation.py` tồn tại                                                 |
| RBAC Enforcement        | 🔥 CRITICAL | `rbac.py` chỉ enum + `has_permission()` — **không middleware, không JWT** |
| Secret Rotation (Auto)  | ⚠️ PARTIAL  | Logic nhưng không scheduler                                               |
| Network Isolation (VPC) | ❌ MISSING  | Không VPC config trong Docker                                             |
| Order Signing           | ❌ MISSING  | Không HMAC/signature                                                      |
| Audit Trail (5-10 năm)  | ❌ MISSING  | Loguru logs nhưng không structured audit store                            |
| Human Override + MFA    | ❌ MISSING  | Không override governance                                                 |
| Trade Surveillance      | ❌ MISSING  | Phát hiện spoofing bên ngoài nhưng không tự kiểm tra                      |

**❌ Missing:** `security/__init__.py`

**Upgrade Tasks:**

- **[NEW]** `security/middleware.py` — FastAPI dependency: JWT + RBAC enforcement
- **[NEW]** `security/audit_store.py` — Append-only DuckDB audit table
- **[NEW]** `security/order_signer.py` — HMAC-SHA256 order signing
- **[NEW]** `security/__init__.py`

---

### 2.15 HA & RELIABILITY — standash §5.2

| Yêu cầu                  | Status          | Chi tiết             |
| ------------------------ | --------------- | -------------------- |
| Uptime ≥ 99.9%           | ❌ NOT VERIFIED | Không SLA monitoring |
| Active/Passive Failover  | ❌ MISSING      | Single-node Docker   |
| Stateful OMS Replication | ❌ MISSING      | In-memory dict       |
| Failover < 5 seconds     | ❌ MISSING      | Không failover test  |

---

### 2.16 TCA (TRANSACTION COST ANALYSIS) — standash §9

**Files:** `analytics/tca_engine.py` (kích thước TBD), `analytics/tca_models.py`, `execution/execution_quality.py` (153L), `execution/slippage_model.py` (127L)

| Yêu cầu                                     | Status     | Chi tiết                                                     |
| ------------------------------------------- | ---------- | ------------------------------------------------------------ |
| Implementation Shortfall                    | ❌ MISSING | `execution_quality.py` có metrics nhưng không IS calculation |
| Slippage Decomposition (Timing/Impact/Fees) | ⚠️ PARTIAL | `slippage_model.py` (127L) — decomposition chưa đầy đủ       |
| Venue Ranking by Fill Quality               | ❌ MISSING | Không per-exchange performance ranking                       |

---

### 2.17 BOT / RUNNER (NỀN TẢNG VẬN HÀNH) — **CHƯA CÓ TRONG standash**

**Files:** `bot/runner.py` (557L), `bot/config.py` (chứa BotConfig), `bot/state.py` (StateMachine), `bot/ev_optimizer.py`, `bot/win_rate_optimizer.py`, `bot/performance.py`

| Đánh giá                                        | Status  | Chi tiết                                               |
| ----------------------------------------------- | ------- | ------------------------------------------------------ |
| Lifecycle Management (Init→WarmUp→Trading→Halt) | ✅ DONE | StateMachine trong `bot/state.py`                      |
| Emergency Shutdown                              | ✅ DONE | `emergency_shutdown()` cancel all tasks, close brokers |
| Multi-venue routing                             | ✅ DONE | `_pick_venue()`, `_adapt_order_for_venue()`            |
| HFT Optimizer integration                       | ✅ DONE | Adaptive signal interval, latency context tracking     |
| EV-based entry filter                           | ✅ DONE | `EVOptimizer` + `WinRateOptimizer`                     |
| Concurrent loops (signal/risk/rebalance)        | ✅ DONE | 3 asyncio tasks                                        |

**🔥 Zero-Latency Violations (7 locations):**

- `runner.py:400` — `await asyncio.sleep(signal_interval)` — main signal loop
- `runner.py:408,412` — `await asyncio.sleep(rebalance_interval_s)` — rebalance wait
- `runner.py:458` — `await asyncio.sleep(rebalance_interval_s)`
- `runner.py:466` — `await asyncio.sleep(0)` — yield control
- `runner.py:488` — `await asyncio.sleep(risk_check_interval_s)` — risk loop timing
- `runner.py:530` — `await asyncio.sleep(1)` — main wait loop

**⚠️ Hardcoded Magic Numbers:**

- `runner.py:290` — `notional = self.config.initial_capital * 0.02` — hardcoded 2% per trade
- `runner.py:105` — `TWAPAlgo(duration_seconds=300, slice_count=5)` — hardcoded TWAP params

**⚠️ Bot dùng `logging` module thay vì `loguru`** — vi phạm Logging Standards trong AGENTS.md

---

### 2.18 META / AUTONOMOUS RESEARCH — **CHƯA CÓ TRONG standash**

**Files:** `meta/` — 9 files (genetic.py 176L, self_evolution.py 148L, multi_agent.py 104L, strategy_generator.py 100L, orchestrator.py 97L, memory.py 93L, self_diagnostic.py 87L, research_loop.py 86L, risk_filter.py 72L)

| Component                            | Status  | Chi tiết                                                      |
| ------------------------------------ | ------- | ------------------------------------------------------------- |
| SystemOrchestrator (ensemble signal) | ✅ DONE | `meta/orchestrator.py` — weighted consensus, adaptive weights |
| GeneticStrategyEvolution             | ✅ DONE | `meta/genetic.py` (176L)                                      |
| MultiAgentPortfolioManager           | ✅ DONE | `meta/multi_agent.py` (104L)                                  |
| StrategyGenerator                    | ✅ DONE | `meta/strategy_generator.py` (100L)                           |
| SelfEvolution                        | ✅ DONE | `meta/self_evolution.py` (148L)                               |
| SelfDiagnostic                       | ✅ DONE | `meta/self_diagnostic.py` (87L)                               |
| ResearchLoop                         | ✅ DONE | `meta/research_loop.py` (86L)                                 |
| RiskFilter                           | ✅ DONE | `meta/risk_filter.py` (72L)                                   |
| Memory (experience replay)           | ✅ DONE | `meta/memory.py` (93L)                                        |

**❌ Missing:** `meta/__init__.py` — package init not present

**⚠️ Assessment:** `meta/` module thể hiện autonomous research capability (Genetic evolution, Self-diagnostic, Multi-agent). Tuy nhiên, tích hợp với production pipeline (`TradingBot` trong `bot/runner.py`) **chưa tồn tại** — đây chỉ là các standalone tools.

---

### 2.19 FEEDBACK ENGINE — **CHƯA CÓ TRONG standash**

**Files:** `feedback/feedback_engine.py` (355L), `feedback/live_feedback_engine.py` (637L)

| Component                                  | Status  | Chi tiết                         |
| ------------------------------------------ | ------- | -------------------------------- |
| Post-trade feedback loop                   | ✅ DONE | `feedback_engine.py` (355L)      |
| Live feedback with regime-aware adjustment | ✅ DONE | `live_feedback_engine.py` (637L) |

**⚠️ `live_feedback_engine.py` line 547**: Commented-out `await asyncio.sleep(300)` — evidence of Zero-Latency awareness nhưng cần verify không còn violations khác.

---

### 2.20 RESEARCH / PIPELINE — **CHƯA CÓ TRONG standash**

**Files:** `research/session.py` (601L), `research/report.py` (160L), `research/metrics.py` (125L), `research/walkforward.py` (82L), `pipeline/research.py` (479L), `pipeline/monitor.py` (222L), `pipeline/deployment.py` (143L), `pipeline/session_bridge.py` (214L)

| Component                                   | Status  | Chi tiết                        |
| ------------------------------------------- | ------- | ------------------------------- |
| ResearchSession (full experiment framework) | ✅ DONE | `research/session.py` (601L)    |
| ResearchPipeline (Data→Feature→Alpha→ML)    | ✅ DONE | `pipeline/research.py` (479L)   |
| LiveMonitor (drift + baseline comparison)   | ✅ DONE | `pipeline/monitor.py` (222L)    |
| DeploymentPipeline (MLflow→bot config)      | ✅ DONE | `pipeline/deployment.py` (143L) |

**🔥 `pipeline/monitor.py:196`** — `await asyncio.sleep(interval_s)` — violation

---

## 3. BỘ VẤN ĐỀ TRÙNG LẶP / DƯ THỪA

| File 1                                        | File 2                                                                | Vấn đề                     | Hành động                            |
| --------------------------------------------- | --------------------------------------------------------------------- | -------------------------- | ------------------------------------ |
| `execution/shadow.py` (30L stub)              | `execution/shadow_engine.py` (295L)                                   | Hai shadow implementations | **DELETE** `shadow.py`               |
| `execution/microprice.py` (nếu có)            | `hft/microprice.py` (72L)                                             | Hai microprice modules     | **DELETE** `execution/microprice.py` |
| `execution/sor.py` (194L)                     | `execution/sor_microprice.py` (nếu có)                                | Hai SOR files              | **MERGE** vào `execution/sor.py`     |
| `risk/portfolio_allocator_enhanced.py` (455L) | `portfolio/allocator.py` (227L)                                       | Allocator trong 2 packages | **MOVE** tất cả vào `portfolio/`     |
| `core/config.py` (65L)                        | `utils/config.py` (65L)                                               | Hai config modules         | **MERGE** vào `core/config.py`       |
| `oms/interface.py` (65L abstract)             | `oms/order_management_system.py` (228L) + `oms/oms_adapter.py` (285L) | OMS scattered              | **CONSOLIDATE**                      |
| `execution/algos.py` (nếu có)                 | `execution/algos/` directory                                          | File và directory cùng tên | **DELETE** standalone file           |

---

## 4. COMPLETE ZERO-LATENCY VIOLATION MAP

> [!CAUTION]
> **38 `asyncio.sleep` + 2 `time.sleep` violations** — nhiều hơn gấp 19 lần so với phân tích trước (2 violations documented).

### `asyncio.sleep` violations (38 locations, 20 files)

| File                                    | Lines                             | Context                                 |
| --------------------------------------- | --------------------------------- | --------------------------------------- |
| `bot/runner.py`                         | 400, 408, 412, 458, 466, 488, 530 | Signal/rebalance/risk loops + main loop |
| `execution/execution_engine.py`         | 383, 395, 492, 504, 528           | Retry, polling, error backoff           |
| `execution/exchange/binance_adapter.py` | 61, 132, 166                      | Rate limit, mock delays                 |
| `execution/reconciliation_service.py`   | 85, 90                            | Periodic recon loop + backoff           |
| `execution/adapters/binance_adapter.py` | 54, 88                            | Mock delays                             |
| `execution/brokers/coinbase.py`         | 99                                | "Simulated network latency"             |
| `execution/latency_model.py`            | 49                                | **Artificial latency injection**        |
| `execution/http.py`                     | 74                                | HTTP retry backoff                      |
| `core/orchestrator.py`                  | 714                               | Main orchestrator loop                  |
| `core/event_bus.py`                     | 95, 133                           | Error backoff, retry delay              |
| `core/resource_monitor.py`              | 132, 136                          | Monitor loop + error backoff            |
| `monitoring/warroom_service.py`         | 90                                | Dashboard broadcast                     |
| `data/market/market_feed.py`            | 62                                | Feed polling                            |
| `data/pipeline/sources/coinbase.py`     | 60, 64                            | WebSocket reconnect                     |
| `data/pipeline/sources/csv_source.py`   | 29                                | Yield control                           |
| `ml/autonomous.py`                      | 122                               | Learning loop                           |
| `backtest/l2_broker_sim.py`             | 67                                | Latency simulation                      |
| `backtest/engine.py`                    | 48                                | Backtest loop                           |
| `pipeline/monitor.py`                   | 196                               | Monitor loop                            |

### `time.sleep` violations (2 locations, 1 file)

| File                             | Lines    | Context                             |
| -------------------------------- | -------- | ----------------------------------- |
| `data/market/coinbase_market.py` | 129, 133 | **BLOCKING** sleep in data pipeline |

### Files dùng `print()` thay vì `loguru` (11 files)

`monitoring/warroom_service.py`, `execution/orderbook_simulator.py`, `execution/algos/pov.py`, `execution/benchmark_orderbook.py`, `portfolio/factor_neutral.py`, `backtest/l2_broker_sim.py`, `ml/meta_online.py`, `feedback/live_feedback_engine.py`, `pipeline/session_bridge.py`, `research/session.py`

---

## 5. MISSING `__init__.py` FILES

Các packages sau thiếu `__init__.py` → import sẽ fail:

| Package                        | Status                |
| ------------------------------ | --------------------- |
| `qtrader/hft/`                 | ❌ MISSING            |
| `qtrader/meta/`                | ❌ MISSING            |
| `qtrader/monitoring/`          | ❌ MISSING            |
| `qtrader/oms/`                 | ⚠️ NEEDS VERIFICATION |
| `qtrader/security/`            | ❌ MISSING            |
| `qtrader/strategy/alpha/`      | ❌ MISSING            |
| `qtrader/strategy/validation/` | ❌ MISSING            |
| `qtrader/utils/`               | ❌ MISSING            |
| `qtrader/validation/`          | ❌ MISSING            |
| `qtrader/execution/adapters/`  | ❌ MISSING            |

---

## 6. CORE PRINCIPLE VIOLATIONS

### 🔥 Zero Latency Rule — §2.4 AGENTS.md

- **38 `asyncio.sleep`** + **2 `time.sleep`** = **40 violations total**
- **Fix bắt buộc:** All timing must be event-driven via candle timestamps or EventBus

### 🔥 No Silent Failure — §2.3

- `reconciliation_engine.py` — Trả về `"MISMATCH"` nhưng không publish event, không halt
- `execution/shadow.py` — `# Logic to calculate shadow fills and pnl...` — silent no-op stub
- `warroom_service.py` — Dùng `print()` thay `loguru`, không Trace ID

### 🔥 Stateless Strategy Design — §2.5

- `core/orchestrator.py` line 305-306 — `self.last_approved_allocation` giữ state nội bộ, mất khi crash
- `bot/runner.py` — `TradingBot` giữ `_last_heartbeat`, `_running`, `_primary_venue` nhưng không persist

### ⚠️ Logging Standard Violations

- `bot/runner.py` dùng `logging.getLogger()` thay vì `loguru`
- 11 files dùng `print()` thay loguru
- Trade entry/exit logs không theo format: `[TRADE] {timestamp} | {symbol} {side} {qty}@{price} | SL={sl} TP={tp} | Reason: {reason}`

---

## 7. PRODUCTION READINESS CHECKLIST

| Hạng mục (standash §12)                 | Status                                      |
| --------------------------------------- | ------------------------------------------- |
| Real-time Recon Verified (fill-by-fill) | ❌ FAIL — không auto-halt khi mismatch      |
| Clock Sync (PTP/NTP)                    | ❌ FAIL — không tồn tại                     |
| TCA Baseline                            | ❌ FAIL — không TCA module hoàn chỉnh       |
| HA Failover Test                        | ❌ FAIL — single-node only                  |
| FSM Validation (stress test)            | ⚠️ PARTIAL — FSM có nhưng không stress test |

> **KẾT LUẬN: 5/5 hạng mục FAIL hoặc PARTIAL. HỆ THỐNG CHƯA ĐẠT PRODUCTION READINESS.**

---

## 8. UPGRADE ROADMAP

### Phase 0 — Immediate Hygiene (1-2 ngày)

| Ưu tiên | Task                                                | Module                                         | Effort |
| ------- | --------------------------------------------------- | ---------------------------------------------- | ------ |
| P0      | Tạo 10+ missing `__init__.py` files                 | Entire codebase                                | Low    |
| P0      | Replace 11 `print()` → `loguru`                     | Multiple files                                 | Low    |
| P0      | Fix TODO comments (3 locations)                     | `orchestrator.py`, `reconciliation_service.py` | Low    |
| P0      | Delete stub files (`shadow.py`, `optimizer.py` 31L) | `execution/`, `portfolio/`                     | Low    |
| P0      | Merge 7 duplicate file pairs                        | Entire codebase                                | Medium |

### Phase 1 — Critical Fixes (1-2 tuần)

| Ưu tiên | Task                                                          | Module                       | Effort |
| ------- | ------------------------------------------------------------- | ---------------------------- | ------ |
| P0      | Fix 40 `asyncio.sleep`/`time.sleep` violations → event-driven | All affected files           | High   |
| P0      | `reconciliation_engine.py` → auto-halt on mismatch            | `execution/`                 | Medium |
| P0      | Shadow PnL implementation + 7-day enforcement                 | `execution/shadow_engine.py` | Medium |
| P0      | RBAC middleware enforcement                                   | `security/`                  | Medium |
| P0      | Persist OMS state (crash recovery)                            | `oms/`                       | Medium |

### Phase 2 — Core Infrastructure (2-4 tuần)

| Ưu tiên | Task                                     | Module        | Effort |
| ------- | ---------------------------------------- | ------------- | ------ |
| P1      | Feed Arbitrator (A/B feeds) + Clock Sync | `data/`       | High   |
| P1      | Event Sourcing + Replay Engine           | `oms/`        | High   |
| P1      | NAV Engine + Cash Ledger                 | `portfolio/`  | Medium |
| P1      | OpenTelemetry trace spans                | `monitoring/` | Medium |
| P1      | Feature Flags hot-reload                 | `core/`       | Low    |
| P1      | War Mode FSM                             | `risk/`       | Medium |
| P1      | Alerting (Telegram/Email)                | `monitoring/` | Medium |

### Phase 3 — Institutional-Grade Hardening (1-3 tháng)

| Ưu tiên | Task                                                     | Module          | Effort    |
| ------- | -------------------------------------------------------- | --------------- | --------- |
| P2      | HA Failover (Active/Passive) + OMS Replication           | Infrastructure  | Very High |
| P2      | Full TCA Engine (IS + Venue Ranking)                     | `analytics/`    | High      |
| P2      | Audit Trail (5-year retention)                           | `security/`     | Medium    |
| P2      | Quote Stuffing Detector                                  | `hft/`          | Medium    |
| P2      | Strategy Lifecycle FSM + Committee Review                | `strategy/`     | High      |
| P2      | QP/Convex Optimization solver                            | `portfolio/`    | High      |
| P2      | Test coverage audit (target >90%)                        | `tests/`        | High      |
| P2      | Integrate `meta/` autonomous research with prod pipeline | `meta/`, `bot/` | High      |

---

## 9. TECHNICAL DEBT INVENTORY

| Loại debt                   | Số lượng     | Chi tiết                                                         |
| --------------------------- | ------------ | ---------------------------------------------------------------- |
| `asyncio.sleep` violations  | 38           | See §4 for full map                                              |
| `time.sleep` violations     | 2            | `data/market/coinbase_market.py`                                 |
| Stub/Empty implementations  | 4+           | `shadow.py`, `optimizer.py`, `rbac.py`                           |
| TODO comments               | 3            | `orchestrator.py:87,397`, `reconciliation_service.py:192`        |
| Magic numbers hardcoded     | 5+           | `max_drawdown=0.20`, `0.02 * capital`, `TWAPAlgo(300,5)`         |
| `print()` instead of loguru | 11 files     | See §4                                                           |
| Missing `__init__.py`       | 10+ packages | See §5                                                           |
| Duplicate files             | 7 pairs      | See §3                                                           |
| Non-loguru logging          | 2+ files     | `bot/runner.py` uses Python `logging` module                     |
| Unintegrated modules        | 1            | `meta/` (autonomous research) — standalone, not in prod pipeline |

---

## 10. DEFINITION OF DONE

Hệ thống đạt **Tier-1 Hedge Fund Grade** khi:

```bash
# DoD Commands — must all pass
ruff check qtrader/ tests/ \
  && mypy qtrader/ --strict \
  && pytest tests/ --cov=qtrader --cov-fail-under=90 \
  && cd rust_core && cargo test

# Production Checklist:
# ✅ Zero asyncio.sleep() in production code paths
# ✅ Zero time.sleep() in production code paths
# ✅ Zero print() in production code — all loguru
# ✅ All __init__.py files present
# ✅ Zero duplicate file pairs
# ✅ Real-time reconciliation with auto-halt verified
# ✅ Clock sync drift < 1ms verified
# ✅ Shadow mode run ≥ 7 days with PnL within tolerance
# ✅ HA failover test < 5s with zero double-execution
# ✅ FSM stress test: 10,000 order transitions with 0 invalid
# ✅ All CRITICAL gaps in this document resolved
# ✅ RBAC middleware enforced on all API endpoints
# ✅ Audit trail persisting to structured store
# ✅ Trade logs follow format: [TRADE] {timestamp} | {symbol} {side} {qty}@{price}
```

---

_Tài liệu được tạo bởi deep scan tự động ngày 2026-03-25. Cập nhật định kỳ sau mỗi sprint._  
_Tham chiếu chuẩn: [standash-document.md](./standash-document.md)_
