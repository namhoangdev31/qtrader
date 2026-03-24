# QTRADER — SYSTEM GAP ANALYSIS REPORT

_Benchmark: [standash-document.md](./standash-document.md) — Tier-1 Hedge Fund Institutional Spec_  
_Generated: 2026-03-24_

---

## EXECUTIVE SUMMARY

| Tier                           | Assessment                     |
| :----------------------------- | :----------------------------- |
| Retail Bot                     | ✅ Vượt xa                     |
| Pro Trader System              | ✅ Đạt                         |
| Prop Trading Firm              | 🟡 Gần đạt (~85%)              |
| Tier-2 Hedge Fund              | 🔴 Thiếu nhiều phần quan trọng |
| Tier-1 (Renaissance/Two Sigma) | 🔴 Chưa đạt                    |

**Tổng thể: ~70–78% so với benchmark Institutional Spec.**

---

## LEGEND

| Symbol | Ý nghĩa                                |
| :----: | :------------------------------------- |
|   ✅   | Đã hoàn thiện, production-ready        |
|   🟡   | Đã có nhưng còn thiếu / cần nâng cấp   |
|   🔴   | Chưa có / placeholder / cần xây từ đầu |
|   🗑️   | Dư thừa, cần dọn dẹp                   |

---

## 1. MARKET DATA LAYER (Tiến độ: 25%)

### 1.1 Hiện trạng

| Module                     | File                                 | Trạng thái | Ghi chú                                                           |
| :------------------------- | :----------------------------------- | :--------: | :---------------------------------------------------------------- |
| Data Pipeline              | `data/pipeline/pipeline.py`          |     🟡     | Có pipeline, chưa có A/B feed                                     |
| Market Feed                | `data/market/market_feed.py`         |     🟡     | Single source, thiếu Feed Arbitration                             |
| OHLCV                      | `data/market/ohlcv.py`               |     ✅     | Cơ bản, hoạt động tốt                                             |
| Data Quality               | `data/quality.py`                    |     🔴     | File tồn tại nhưng thiếu Z-score Outlier và Cross-exchange Sanity |
| Stale Detection            | _(không có)_                         |     🔴     | Chưa có                                                           |
| Sequence ID / Gap Detector | _(không có)_                         |     🔴     | Chưa có bộ phát hiện Gap và Snapshot Recovery                     |
| Feed Arbitration (A/B)     | _(không có)_                         |     🔴     | Chưa có                                                           |
| Clock / PTP Sync           | _(không có)_                         |     🔴     | Không có bất kỳ cơ chế nào                                        |
| Streaming (Coinbase)       | `data/pipeline/sources/streaming.py` |     🟡     | Chỉ 1 sàn                                                         |

### 1.2 Yêu cầu kỹ thuật cần bổ sung

```markdown
# PROMPT: Data Quality Gate
Implement `qtrader/data/quality_gate.py`:
- Class `DataQualityGate`:
  - `check_outlier(series: pl.Series, method="zscore", threshold=3.0) -> bool`
  - `check_stale(ts: float, max_age_ms: int = 5000) -> bool`
  - `check_cross_exchange_sanity(prices: dict[str, float], max_spread_pct=0.01) -> bool`
  - `check_sequence_gap(seq_id: int, last_seq_id: int) -> bool`
- Phải raise `DataQualityError` khi fail
- Phải log chi tiết với `loguru`
```

---

## 2. ALPHA ENGINE & FEATURE FACTORY (Tiến độ: 80%)

### 2.1 Hiện trạng

| Module                 | File                         | Trạng thái | Ghi chú                                    |
| :--------------------- | :--------------------------- | :--------: | :----------------------------------------- |
| Alpha Base             | `alpha/base.py`              |     ✅     | Tốt                                        |
| Factor Model           | `alpha/factor_model.py`      |     ✅     | Có IC, Decay                               |
| Technical Alpha        | `alpha/technical.py`         |     ✅     | Vectorized Polars                          |
| Microstructure         | `alpha/microstructure.py`    |     🟡     | Có Imbalance nhưng thiếu Adverse Selection |
| Feature Engine         | `features/engine.py`         |     ✅     | Tốt                                        |
| Feature Neutralization | `features/neutralization.py` |     🟡     | Tồn tại nhưng chưa dùng Convex QP solver   |
| Feature Store          | `features/store.py`          |     🟡     | Chưa có versioning, lineage tracking       |
| Look-ahead Bias Test   | `tests/`                     |     🟡     | Cần kiểm tra thực tế coverage              |

### 2.2 Yêu cầu kỹ thuật cần bổ sung

```markdown
# PROMPT: Point-in-Time Integrity Test
In `tests/unit/alpha/test_factor_model.py`, add:
- def test_no_lookahead_bias():
    """compute(df_past)[i] == compute(df_full)[i] for all i"""
    # Call factor with df_past and df_full, assert row-level equality

# PROMPT: Feature Store Lineage
Upgrade `qtrader/features/store.py`:
- Add `feature_lineage: dict[str, FeatureMetadata]` where FeatureMetadata has:
  - source_columns: list[str]
  - compute_version: str (git hash or timestamp)
  - dataset_snapshot_id: str
```

---

## 3. FEATURE VALIDATION (Tiến độ: 85%)

### 3.1 Hiện trạng

| Module               | File                                       | Trạng thái | Ghi chú                                              |
| :------------------- | :----------------------------------------- | :--------: | :--------------------------------------------------- |
| Feature Validator    | `risk/feature_validation.py`               |     ✅     | IC, Decay, PSI                                       |
| Strategy Validator   | `strategy/validation/feature_validator.py` |     🟡     | Giống file trên, có thể trùng lặp                    |
| Validation module    | `validation/feature_validator.py`          |     🗑️     | TRÙNG LẶP — cần merge lại 1 file                     |
| Auto-disable trigger | _(không có)_                               |     🔴     | PSI check có nhưng chưa có action tự disable feature |

### 3.2 Yêu cầu kỹ thuật

```markdown
# PROMPT: Auto-disable Feature
In `qtrader/risk/feature_validation.py`:
- Add method `auto_disable_if_drift(feature_name: str, psi_threshold=0.15) -> bool`
- If PSI > threshold: mark feature disabled in FeatureRegistry
- Log: logger.warning(f"[DRIFT] Feature {feature_name} disabled. PSI={psi:.3f}")
- Return True if disabled
```

---

## 4. STRATEGY ENGINE (Tiến độ: 75%)

### 4.1 Hiện trạng

| Module                 | File                                 | Trạng thái | Ghi chú                                           |
| :--------------------- | :----------------------------------- | :--------: | :------------------------------------------------ |
| Probabilistic Strategy | `strategy/probabilistic_strategy.py` |     ✅     | Tốt                                               |
| Ensemble Strategy      | `strategy/ensemble.py`               |     ✅     | Có                                                |
| Meta Strategy          | `strategy/meta_strategy.py`          |     ✅     | Có                                                |
| Regime Meta Strategy   | `strategy/regime_meta_strategy.py`   |     ✅     | Liên kết với Regime Detector                      |
| Strategy Sandbox       | _(không có)_                         |     🔴     | Không có isolated capital/risk limit per strategy |
| Dynamic Weight         | `strategy/ensemble_strategy.py`      |     🟡     | Cần xác minh còn sử dụng fixed weights không      |

---

## 5. PORTFOLIO ALLOCATOR (Tiến độ: 45%)

### 5.1 Hiện trạng

| Module                 | File                             | Trạng thái | Ghi chú                                                                                |
| :--------------------- | :------------------------------- | :--------: | :------------------------------------------------------------------------------------- |
| Base Allocator         | `portfolio/allocator.py`         |     🔴     | **`SimpleAllocator` chỉ phân bổ theo signal strength. KHÔNG có Risk Parity thực thụ.** |
| Capital Allocator      | `portfolio/capital_allocator.py` |     🟡     | Cần xem chi tiết                                                                       |
| HRP                    | `portfolio/hrp.py`               |     ✅     | Hierarchical Risk Parity có                                                            |
| Kelly Criterion        | `portfolio/kelly.py`             |     ✅     | Có                                                                                     |
| Portfolio Optimization | `portfolio/optimization.py`      |     🟡     | Tồn tại nhưng cần check có dùng QP không                                               |
| Factor Neutralization  | `features/neutralization.py`     |     🟡     | Beta/Market neutral chưa production-grade                                              |
| Convex Optimization    | _(không có thư viện CVXPY)_      |     🔴     | Constraint solver chưa dùng QP/Convex                                                  |
| Exposure Decomposition | `risk/factor_risk.py`            |     🟡     | Có nhưng chưa đầy đủ Sector/Factor                                                     |

### 5.2 Yêu cầu kỹ thuật

```markdown
# PROMPT: Institutional Portfolio Construction
Upgrade `qtrader/portfolio/allocator.py`:
1. Implement `RiskParityAllocator(AllocatorBase)`:
   - True risk parity: allocate so each asset contributes equally to total portfolio vol
   - NOT inverse volatility (must use covariance matrix)
   - Use `scipy.optimize.minimize` or `cvxpy` as solver

2. Implement `FactorNeutralAllocator(AllocatorBase)`:
   - Compute exposure to market beta, sector, momentum factor
   - Apply neutralization constraints

3. Expose `ExposureReport` dataclass with:
   - sector_exposure: dict[str, float]
   - factor_exposure: dict[str, float] (beta, momentum, vol)
```

---

## 6. RISK ENGINE (Tiến độ: 95%)

### 6.1 Hiện trạng — ĐIỂM MẠNH NHẤT CỦA HỆ THỐNG

| Module                | File                          | Trạng thái | Ghi chú                                                                     |
| :-------------------- | :---------------------------- | :--------: | :-------------------------------------------------------------------------- |
| Runtime Risk Engine   | `risk/runtime_risk_engine.py` |     ✅     | VaR, Drawdown, Kill Switch, Leverage, Concentration — rất tốt               |
| Real-time Risk        | `risk/realtime.py`            |     ✅     | Real-time assessment                                                        |
| Drawdown Control      | `risk/drawdown_control.py`    |     ✅     | Riêng biệt, chi tiết                                                        |
| Factor Risk           | `risk/factor_risk.py`         |     ✅     | Factor decomposition                                                        |
| Network Kill Switch   | `risk/network_kill_switch.py` |     🟡     | Có, nhưng cần check timeout < 2s                                            |
| Limits                | `risk/limits.py`              |     ✅     | Pre-trade gates                                                             |
| Fat-finger Protection | `risk/limits.py`              |     🟡     | Tồn tại, cần kiểm tra có Price deviation check không                        |
| Regime-aware Limits   | _(chưa nối)_                  |     🔴     | RegimeDetector tồn tại nhưng Risk Engine chưa đọc regime để thay đổi limits |

### 6.2 Yêu cầu kỹ thuật

```markdown
# PROMPT: Regime-aware Risk Integration
In `qtrader/risk/runtime_risk_engine.py`:
- Add `set_regime(regime_id: int) -> None`
- Adjust `var_threshold`, `max_leverage`, `max_position_size` based on regime:
  - regime 0 (low vol): normal limits
  - regime 1 (high vol): reduce leverage by 40%, tighten var_threshold by 30%
  - regime 2 (crisis): halve all limits
- Source regime from `qtrader.ml.regime_detector.RegimeDetector.get_current_regime()`
```

---

## 7. EXECUTION ENGINE & SOR (Tiến độ: 70%)

### 7.1 Hiện trạng

| Module                 | File                                     | Trạng thái | Ghi chú                                     |
| :--------------------- | :--------------------------------------- | :--------: | :------------------------------------------ |
| Execution Engine       | `execution/execution_engine.py`          |     ✅     | Async, non-blocking                         |
| VWAP                   | `execution/algos/vwap.py`                |     ✅     | Có                                          |
| TWAP                   | `execution/algos/twap.py`                |     ✅     | Có                                          |
| POV                    | `execution/algos/pov.py`                 |     ✅     | Có                                          |
| Smart Router           | `execution/smart_router.py`              |     🟡     | Có routing nhưng thiếu Micro-price logic    |
| SOR                    | `execution/sor.py`                       |     🟡     | Tồn tại, cần check fee-aware decision       |
| Orderbook Core         | `execution/orderbook_core.py`            |     🟡     | Có nhưng thiếu Queue position modeling      |
| Global Unique Order ID | _(không có)_                             |     🔴     | Không có UUID + Exchange Prefix + Timestamp |
| Adversarial Model      | _(không có)_                             |     🔴     | Không có Toxic Flow, Spoofing Detection     |
| Binance Adapter        | `execution/adapters/binance_adapter.py`  |     🟡     | Có                                          |
| Coinbase Adapter       | `execution/exchange/coinbase_adapter.py` |     🟡     | Có                                          |

### 7.2 Yêu cầu kỹ thuật

```markdown
# PROMPT: Global Unique Order ID
Create `qtrader/execution/order_id.py`:
- `generate_order_id(exchange: str, symbol: str) -> str`
  - Format: "{UUID4}-{EXCHANGE}-{timestamp_ns}"
  - Must be collision-free across exchanges and retries
  - Store in-memory registry to detect duplicates
  - `is_duplicate(order_id: str) -> bool`

# PROMPT: Adversarial Market Model (minimal viable)
Create `qtrader/execution/adversarial.py`:
- `ToxicFlowDetector`:
  - `detect(orderbook: pl.DataFrame, fill_history: list[FillEvent]) -> float`
  - Computes adverse selection probability (0–1)
  - Input: recent fills vs orderbook imbalance
  - Output: "toxicity score" — if > threshold, reduce order size
```

---

## 8. OMS & RECONCILIATION (Tiến độ: 35%)

### 8.1 Hiện trạng

| Module                 | File                                  | Trạng thái | Ghi chú                                                                                          |
| :--------------------- | :------------------------------------ | :--------: | :----------------------------------------------------------------------------------------------- |
| Unified OMS            | `execution/oms.py`                    |     ✅     | FIFO PnL, realized/unrealized tracking tốt                                                       |
| OMS Adapter            | `execution/oms_adapter.py`            |     🟡     | Bridge với exchange                                                                              |
| Reconciliation Service | `execution/reconciliation_service.py` |     🔴     | **Toàn bộ `_get_local_positions()` và `_get_exchange_positions()` là placeholder — return `{}`** |
| Event-driven Recon     | _(không có)_                          |     🔴     | Chỉ có periodic loop, không có fill-triggered recon                                              |
| Official OMS Interface | `oms/interface.py`                    |     🗑️     | Khác với `execution/oms.py` — gây nhầm lẫn                                                       |
| Order FSM              | _(không có)_                          |     🔴     | Không có State Machine (NEW→ACK→FILLED...) chuẩn hóa                                             |
| Hard Mismatch Halt     | _(không có)_                          |     🔴     | Không có trigger halt khi position drift                                                         |

### 8.2 Yêu cầu kỹ thuật (CRITICAL — ƯU TIÊN CAO NHẤT)

```markdown
# PROMPT: Fix Reconciliation Service (CRITICAL)
Fix `qtrader/execution/reconciliation_service.py`:
1. Implement `_get_local_positions()` by reading `self.local_oms.position_manager.get_all_positions()`
2. Implement `_get_exchange_positions()` by calling `self.exchange_client.get_positions()`
3. On mismatch > 0: call `self._halt_trading()` which fires a kill_switch event
4. After each FillEvent: call `reconcile_single_fill(fill: FillEvent)` for real-time recon

# PROMPT: Order FSM
Create `qtrader/execution/order_fsm.py`:
- `OrderState` enum: NEW, ACK, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED
- `OrderFSM` class:
  - `transition(order_id: str, new_state: OrderState) -> None`
  - Raises `InvalidTransitionError` for illegal jumps (e.g., NEW -> FILLED without ACK)
  - Maintains `order_history: dict[str, list[OrderState]]` for audit
```

---

## 9. MLOPS & DRIFT MONITORING (Tiến độ: 90%)

### 9.1 Hiện trạng

| Module               | File                          | Trạng thái | Ghi chú                                            |
| :------------------- | :---------------------------- | :--------: | :------------------------------------------------- |
| MLflow Manager       | `ml/mlflow_manager.py`        |     ✅     | Model versioning, tracking                         |
| Regime Detector      | `ml/regime_detector.py`       |     ✅     | GMM-based, online update                           |
| Drift                | `analytics/drift.py`          |     ✅     | PSI, KS test                                       |
| Drift Detector       | `analytics/drift_detector.py` |     🟡     | Trùng lắp với analytics/drift.py                   |
| Shadow Engine        | `execution/shadow_engine.py`  |     ✅     | Có                                                 |
| Shadow (simple)      | `execution/shadow.py`         |     🗑️     | Trùng lặp, cần gộp                                 |
| Model Registry       | `ml/registry.py`              |     🟡     | Có nhưng cần kiểm tra có versioning metadata không |
| Auto-retrain trigger | _(chưa tích hợp)_             |     🔴     | Drift detection chưa tự động trigger retrain       |

---

## 10. HFT & CLOCK INFRASTRUCTURE (Tiến độ: 15%)

### 10.1 Hiện trạng

| Module               | File                         | Trạng thái | Ghi chú                                            |
| :------------------- | :--------------------------- | :--------: | :------------------------------------------------- |
| HFT Optimizer        | `hft/optimizer.py`           |     🟡     | Tồn tại, cần xem chi tiết                          |
| Latency Model        | `execution/latency_model.py` |     🟡     | Có model nhưng chưa rõ stage-by-stage              |
| Clock Sync (NTP/PTP) | _(không có)_                 |     🔴     | **Không có bất kỳ clock synchronization nào**      |
| Resource Monitor     | `core/resource_monitor.py`   |     🟡     | CPU/Mem monitor có, nhưng không có latency heatmap |
| Telemetry            | `analytics/telemetry.py`     |     🟡     | Có nhưng chưa kết nối với War Room Dashboard       |

### 10.2 Yêu cầu kỹ thuật

```markdown
# PROMPT: Clock Sync Module
Create `qtrader/core/clock.py`:
- `ClockSync`:
  - `get_ns() -> int`: Returns nanosecond timestamp, NTP-corrected
  - `sync_offset_ms() -> float`: Returns current drift vs NTP server
  - `is_drifted(threshold_ms=5.0) -> bool`
  - Log warning if drift > threshold
- Integrate into MarketFeed: every tick timestamp must go through ClockSync.get_ns()
```

---

## 11. DATA GOVERNANCE & CAPITAL ACCOUNTING (Tiến độ: 10%)

### 11.1 Hiện trạng

| Module                    | File               | Trạng thái | Ghi chú                             |
| :------------------------ | :----------------- | :--------: | :---------------------------------- |
| PnL (Realized/Unrealized) | `execution/oms.py` |     ✅     | Phân tách tốt trong PositionManager |
| NAV Calculation           | _(không có)_       |     🔴     | Không có EOD NAV chốt sổ            |
| Fee Accrual               | _(không có)_       |     🔴     | Không track fee theo thời gian      |
| Funding Rate Tracking     | _(không có)_       |     🔴     | Không có                            |
| Cash Ledger               | _(không có)_       |     🔴     | Multi-currency không có             |
| Dataset Versioning        | _(không có)_       |     🔴     | Chưa có version ID cho dataset      |
| Data Lake                 | `data/datalake.py` |     🟡     | Có data lake nhưng thiếu versioning |

### 11.2 Yêu cầu kỹ thuật

```markdown
# PROMPT: Capital Accounting Layer
Create `qtrader/portfolio/accounting.py`:
- `CapitalLedger`:
  - `record_fee(exchange: str, symbol: str, fee: float, timestamp: int) -> None`
  - `record_funding_rate(symbol: str, rate: float, timestamp: int) -> None`
  - `get_nav(prices: dict[str, float]) -> float` → total portfolio NAV
  - `get_daily_pnl(date: str) -> float` → EOD PnL
  - `get_total_fees_accrued(start: int, end: int) -> float`
  - Multi-currency: store in USD equivalent
```

---

## 12. SECURITY & INFRASTRUCTURE (Tiến độ: 20%)

### 12.1 Hiện trạng

| Module            | File                   | Trạng thái | Ghi chú                                          |
| :---------------- | :--------------------- | :--------: | :----------------------------------------------- |
| Secrets (.env)    | `.env`, `.env.example` |     🟡     | Có env file, nhưng không có rotation             |
| RBAC              | _(không có)_           |     🔴     | Không có phân quyền                              |
| Network Isolation | `docker-compose.yml`   |     🟡     | Có Docker network nhưng chưa VPC-grade           |
| Order Signing     | _(không có)_           |     🔴     | Không có                                         |
| Secret Rotation   | _(không có)_           |     🔴     | Manual                                           |
| HA Failover       | _(không có)_           |     🔴     | Không có Active/Passive hoặc Active/Active setup |

---

## 13. TESTING COVERAGE (Tiến độ: 50%)

### 13.1 Hiện trạng

```
tests/
├── unit/      ← có structure nhưng cần kiểm tra coverage thực tế
└── integration/ ← cần xác minh
```

```bash
# Chạy để biết coverage thực tế:
pytest tests/ --cov=qtrader --cov-report=term-missing --cov-fail-under=90
```

| Test Category                  | Trạng thái | Ghi chú                    |
| :----------------------------- | :--------: | :------------------------- |
| Unit tests cho Risk Engine     |     🟡     | Cần verify >90%            |
| Unit tests cho OMS/FSM         |     🔴     | FSM chưa có                |
| Integration: Full pipeline     |     🟡     | Cần xác minh               |
| Look-ahead bias test           |     🔴     | Chưa có explicit test      |
| Stress test: High vol scenario |     🔴     | Chưa có                    |
| Mock external connections      |     🟡     | Cần verify tất cả đều mock |

---

## 14. DƯ THỪA CẦN DỌN DẸP

| File dư thừa                                            | Lý do                                      | Hành động                   |
| :------------------------------------------------------ | :----------------------------------------- | :-------------------------- |
| `validation/feature_validator.py`                       | Duplicate của `risk/feature_validation.py` | Xóa, dùng 1 file            |
| `oms/interface.py`                                      | Không rõ quan hệ với `execution/oms.py`    | Audit → merge hoặc xóa      |
| `execution/shadow.py`                                   | Duplicate của `execution/shadow_engine.py` | Xóa, giữ `shadow_engine.py` |
| `analytics/drift.py` vs `analytics/drift_detector.py`   | Chồng lấn                                  | Merge thành 1 module        |
| `execution/algos.py` (file) vs `execution/algos/` (dir) | Cùng tên, gây nhầm lẫn                     | Gộp thành 1 directory       |

---

## 15. PRODUCTION READINESS CHECKLIST

| Hạng mục                                      | Trạng thái |
| :-------------------------------------------- | :--------: |
| ✅ Risk Engine (VaR + Drawdown + Kill Switch) |     ✅     |
| ✅ Execution algos (VWAP/TWAP/POV)            |     ✅     |
| ✅ Regime Detection (GMM)                     |     ✅     |
| ✅ MLflow tracking                            |     ✅     |
| 🔴 Reconciliation (event-driven fill-by-fill) |     🔴     |
| 🔴 Order FSM formalized                       |     🔴     |
| 🔴 Clock Sync (NTP/PTP)                       |     🔴     |
| 🔴 Global Unique Order ID                     |     🔴     |
| 🔴 Capital Accounting (NAV, Fee Accrual)      |     🔴     |
| 🔴 Portfolio: True Risk Parity (Convex QP)    |     🔴     |
| 🔴 Data Quality Gate (Pre-alpha)              |     🔴     |
| 🔴 Regime → Risk Limits coupling              |     🔴     |
| 🔴 Test coverage >90% verified                |     🔴     |
| 🔴 War Room Dashboard                         |     🔴     |

---

## 16. ROADMAP TRIỂN KHAI (ƯU TIÊN)

### Phase 1 — Critical Fixes (2 tuần)

1. **Fix Reconciliation Service** — implement `_get_local_positions()` và `_get_exchange_positions()` thực sự.
2. **Implement Order FSM** — `order_fsm.py` với state transition validation.
3. **Global Order ID** — `order_id.py` với UUID + exchange prefix.
4. **Data Quality Gate** — `quality_gate.py` với Outlier + Stale checks.

### Phase 2 — Institutional Upgrades (3 tuần)

1. **Capital Accounting Layer** — `portfolio/accounting.py`.
2. **True Risk Parity Allocator** — QP-based `RiskParityAllocator`.
3. **Regime → Risk Coupling** — `runtime_risk_engine.set_regime()`.
4. **Clock Sync** — `core/clock.py` với NTP drift detection.

### Phase 3 — War Room & Security (2 tuần)

1. **TCA Module** — Slippage decomposition post-trade.
2. **Dọn dẹp Duplicates** — Các file dư thừa.
3. **Security Hardening** — RBAC, Secret Rotation.
4. **War Room Dashboard** — Live PnL/Risk/Latency metrics.

---

## 17. CÁC PROMPT MẪU ĐỂ GIAO CHO AI

> Copy đoạn dưới đây làm context khi yêu cầu AI implement từng module.

```markdown
# Prompt Context Template

```python
Tôi đang phát triển hệ thống QTrader — Hedge Fund-grade Quant Trading System.
- Language: Python 3.12+
- Data: Polars (NO pandas in loops)
- Async: asyncio
- Logging: loguru (format: [TRADE] {timestamp} | {symbol} {side} {qty}@{price} | SL={sl} TP={tp} | Reason: {reason})
- Types: 100% type hints, mypy --strict must pass
- Tests: pytest, mock external connections, >90% coverage

Architecture:
- qtrader/execution/ → OMS, Execution Engine, SOR, Exchange Adapters
- qtrader/risk/ → Risk Engine, Kill Switch, Limits
- qtrader/portfolio/ → Allocator, HRP, Kelly
- qtrader/alpha/ → Feature Factory, Alphas
- qtrader/ml/ → MLflow, Regime Detector, Models
- qtrader/core/ → Event Bus, Config, Logger, Clock

Benchmark spec: standash-document.md (Tier-1 Institutional)
Current gap: [mô tả gap cụ thể từ system-gap-analysis.md]
```

---

> [!CAUTION]
> **Reconciliation Service** là điểm yếu nguy hiểm nhất hiện tại — toàn bộ logic `_get_local_positions()` và `_get_exchange_positions()` đang trả về `{}` (empty dict), nghĩa là hệ thống **KHÔNG đang reconcile gì cả**. Đây phải là ưu tiên Fix #1 trước bất kỳ thứ gì khác.
