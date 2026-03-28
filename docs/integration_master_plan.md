# QTRADER — INTEGRATION MASTER PLAN

> **Mục tiêu**: Tài liệu phân tích tổng hợp từ `system-gap-analysis.md` và `audit_output.md`, chỉ dẫn chính xác từng file/method/module cần được tích hợp, hợp nhất hoặc xoá — chia thành các phase thực thi để hệ thống tiến tới chuẩn Tier-1 Institutional theo `standash-document.md`.
>
> **Nguyên tắc**: Mỗi phase phải tự hoàn chỉnh (self-contained), có thể test và verify độc lập.

---

## MỤC LỤC

1. [PHÂN TÍCH TỔNG QUAN](#1-phân-tích-tổng-quan)
2. [PHASE 0: STRUCTURAL FIX — Package Init](#phase-0)
3. [PHASE 1: DUPLICATE CONSOLIDATION — Hợp nhất 18 cụm trùng lặp](#phase-1)
4. [PHASE 2: ORPHAN INTEGRATION — Tích hợp file mồ côi](#phase-2)
5. [PHASE 3: INFRASTRUCTURE WIRING — Nối 6 authority từ Phase -1](#phase-3)
6. [PHASE 4: STUB COMPLETION — Hoàn thiện logic giả](#phase-4)
7. [PHASE 5: DEAD CODE REMOVAL — Xoá file thừa](#phase-5)
8. [PHASE 6: DEEP DISCIPLINE FIX — Latency, Precision, Concurrency](#phase-6)
9. [PHASE 7: INTEGRATION TEST & VERIFICATION](#phase-7)

---

## 1. PHÂN TÍCH TỔNG QUAN

### Hiện trạng hệ thống

| Metric | Giá trị | Nguồn |
|:---|:---|:---|
| Tổng file Python | 427 | audit_output |
| Tổng LOC | 56,890 | audit_output |
| Module (thư mục) | 34 | audit_output |
| File orphaned (mồ côi) | ~80 | gap-analysis |
| Cụm trùng lặp | 18 | gap-analysis |
| Thư mục thiếu `__init__.py` | 15 | Scan thực tế |
| Stub methods (trả `{}`, `[]`) | ~60 | gap-analysis |
| Infrastructure orphaned | 6/6 | audit_output |
| Điểm audit tổng | 0.4567 (F) | audit_output |
| Standash compliance | 77% isolated, 55% wired | gap-analysis |

### Vấn đề cốt lõi

**Infrastructure-Integration Gap**: Hệ thống có đầy đủ components nhưng thiếu "dây nối" (connective tissue). Code tồn tại nhưng wiring thì không.

---

## PHASE 0: STRUCTURAL FIX — Package & Init {#phase-0}

> **Mục tiêu**: Mọi thư mục Python phải importable. Không có package nào bị broken.
> **Ước lượng**: ~30 phút

### Tạo `__init__.py` cho 15 thư mục thiếu

| # | Thư mục | Số file bên trong | Tác động |
|---|---------|-------------------|----------|
| 1 | `qtrader/tca/` | 6 | TCA module hoàn toàn unimportable |
| 2 | `qtrader/feedback/` | 2 | Incident handler unimportable |
| 3 | `qtrader/verification/` | 1 | ReplayValidator unimportable |
| 4 | `qtrader/system/` | 2 | System orchestrator unimportable |
| 5 | `qtrader/governance/` | 6 | Fund governance unimportable |
| 6 | `qtrader/portfolio/` | 14 | Capital accounting unimportable |
| 7 | `qtrader/api/` | 1+ | API endpoints unimportable |
| 8 | `qtrader/meta_control/` | ? | Meta control unimportable |
| 9 | `qtrader/events/` | ? | Events unimportable |
| 10 | `qtrader/execution/microstructure/` | 6 | Microstructure analysis unimportable |
| 11 | `qtrader/execution/core/` | 1 | Fill probability unimportable |
| 12 | `qtrader/execution/routing/` | 4 | Smart routing unimportable |
| 13 | `qtrader/execution/rl/` | 4 | RL execution unimportable |
| 14 | `qtrader/execution/strategy/` | 2 | Execution strategy unimportable |
| 15 | `qtrader/tca/report_templates/` | ? | TCA templates unimportable |

---

## PHASE 1: DUPLICATE CONSOLIDATION — Hợp nhất 18 cụm trùng lặp {#phase-1}

> **Mục tiêu**: Mỗi domain chỉ có 1 canonical implementation duy nhất.
> **Ước lượng**: 2-3 ngày

### 1.1 Kill Switch → Canonical: `risk/kill_switch.py`

| File | Hành động | Lý do |
|------|-----------|-------|
| `risk/kill_switch.py` (GlobalKillSwitch) | ✅ **GIỮ LẠI** — Là canonical | Active, tích hợp vào orchestrator |
| `governance/kill_switch.py` (127 LOC) | 🔴 **XOÁ** | Orphan, logic trùng với risk/ |
| `risk/network_kill_switch.py` | 🔀 **HỢP NHẤT** vào `risk/kill_switch.py` | Logic network-specific cần merge vào canonical |

### 1.2 Portfolio Allocator → Canonical: `risk/portfolio/allocator.py`

| File | Hành động | Lý do |
|------|-----------|-------|
| `risk/portfolio/allocator.py` | ✅ **GIỮ LẠI** — Là canonical | Tích hợp QP solver |
| `portfolio/allocator.py` | 🔀 **HỢP NHẤT** feature vào canonical rồi xoá | Có logic khác biệt nhưng trùng domain |
| `portfolio/reallocator.py` | 🔴 **XOÁ** | Orphan, không ai import |
| `risk/portfolio/capital_allocator.py` | 🔀 **HỢP NHẤT** rồi xoá | Active duplicate |
| `risk/portfolio_allocator_enhanced.py` | 🔀 **HỢP NHẤT** rồi xoá | Active duplicate |
| `meta/capital_allocator.py` (144 LOC) | 🔴 **XOÁ** | Orphan, meta-level allocator không cần thiết |

### 1.3 Accounting / NAV / Fees → Canonical: `analytics/`

| File | Hành động | Lý do |
|------|-----------|-------|
| `analytics/accounting.py` | ✅ **GIỮ LẠI** — Là canonical PnL | Active |
| `analytics/fee_engine.py` | ✅ **GIỮ LẠI** — Là canonical Fees | Active |
| `risk/portfolio/accounting.py` | 🔴 **XOÁ** | Duplicate |
| `risk/portfolio/fees.py` | 🔴 **XOÁ** | Duplicate |
| `portfolio/fee_engine.py` (94 LOC) | 🟡 **ĐÁNH GIÁ** → Merge logic vào `analytics/fee_engine.py` rồi xoá | Orphan nhưng có thể có logic khác biệt |
| `portfolio/nav_engine.py` (84 LOC) | 🔵 **TÍCH HỢP** vào `analytics/accounting.py` | Standash §4.14 yêu cầu NAV |
| `portfolio/cash_ledger.py` (97 LOC) | 🔵 **TÍCH HỢP** vào `analytics/accounting.py` | Standash §4.14 yêu cầu Cash Ledger |
| `portfolio/funding_engine.py` (123 LOC) | 🔵 **TÍCH HỢP** vào `analytics/accounting.py` | Standash §4.14 yêu cầu Funding Tracking |

### 1.4 Orchestrator → Canonical: `core/orchestrator.py` + `core/global_orchestrator.py`

| File | Hành động | Lý do |
|------|-----------|-------|
| `core/orchestrator.py` (726 LOC) | ✅ **GIỮ LẠI** — Là brain chính | Active, largest |
| `core/global_orchestrator.py` (162 LOC) | ✅ **GIỮ LẠI** — Bổ trợ kill switch logic | Khác responsibility |
| `meta/orchestrator.py` (97 LOC) | 🔴 **XOÁ** | Orphan, logic trùng |
| `system/system_orchestrator.py` (122 LOC) | 🔴 **XOÁ** | Orphan, logic trùng |
| `data/pipeline/orchestrator.py` | ✅ **GIỮ LẠI** | Data-specific, khác domain |

### 1.5 Order FSM → Canonical: `oms/order_fsm.py`

| File | Hành động |
|------|-----------|
| `oms/order_fsm.py` | ✅ **GIỮ LẠI** |
| `execution/order_fsm.py` | 🔴 **XOÁ** — Duplicate orphan |

### 1.6 Reconciliation → Canonical: `execution/reconciliation_engine.py`

| File | Hành động |
|------|-----------|
| `execution/reconciliation_engine.py` | ✅ **GIỮ LẠI** |
| `execution/reconciliation_service.py` | 🔴 **XOÁ** — Duplicate orphan |

### 1.7 Slippage → Canonical: `execution/slippage_model.py`

| File | Hành động |
|------|-----------|
| `execution/slippage_model.py` | ✅ **GIỮ LẠI** |
| `execution/slippage_control.py` (113 LOC) | 🔀 **HỢP NHẤT** control logic vào canonical rồi xoá |
| `tca/slippage.py` (175 LOC) | 🔵 **GIỮ** — khác domain (TCA analytics) |

### 1.8 Microprice & Imbalance → Canonical: `execution/microstructure/`

| File | Hành động |
|------|-----------|
| `execution/microstructure/microprice.py` | ✅ **GIỮ LẠI** |
| `execution/microstructure/imbalance.py` | ✅ **GIỮ LẠI** |
| `hft/microprice.py` | 🔴 **XOÁ** — Duplicate |
| `hft/imbalance.py` | 🔴 **XOÁ** — Duplicate |

### 1.9 RL Agent → Canonical: `execution/rl/agent.py`

| File | Hành động |
|------|-----------|
| `execution/rl/agent.py` | ✅ **GIỮ LẠI** |
| `execution/rl_agent.py` | 🔴 **XOÁ** |
| `hft/rl_agent.py` | 🔴 **XOÁ** |

### 1.10 Cost Model → Canonical: `execution/cost_model.py`

| File | Hành động |
|------|-----------|
| `execution/cost_model.py` | ✅ **GIỮ LẠI** |
| `execution/routing/cost_model.py` (114 LOC) | 🔀 **HỢP NHẤT** rồi xoá |

### 1.11 Position Sizing → Canonical: `risk/portfolio/position_sizing.py`

| File | Hành động |
|------|-----------|
| `risk/portfolio/position_sizing.py` | ✅ **GIỮ LẠI** |
| `risk/portfolio/sizing.py` | 🔀 **HỢP NHẤT** rồi xoá |
| `risk/position_sizer.py` | 🔀 **HỢP NHẤT** rồi xoá |
| `portfolio/position_sizing.py` | 🔴 **XOÁ** — Orphan duplicate |

### 1.12 Regime Detection → Canonical: `ml/regime.py`

| File | Hành động |
|------|-----------|
| `ml/regime.py` (337 LOC) | ✅ **GIỮ LẠI** |
| `ml/regime_detector.py` (463 LOC) | 🔀 **HỢP NHẤT** logic bổ sung rồi xoá |
| `ml/hmm_regime.py` | 🔀 **HỢP NHẤT** HMM model rồi xoá |

### 1.13 TCA → Giữ cả hai domain nhưng kết nối

| File | Hành động | Lý do |
|------|-----------|-------|
| `analytics/tca_engine.py` | ✅ **GIỮ LẠI** | Active, integrated |
| `analytics/tca_models.py` | ✅ **GIỮ LẠI** | Active |
| `tca/venue_ranking.py` (165 LOC) | 🔵 **TÍCH HỢP** | Import vào execution pipeline — Standash §9 |
| `tca/cost_attribution.py` (150 LOC) | 🔵 **TÍCH HỢP** | Import vào analytics |
| `tca/implementation_shortfall.py` (135 LOC) | 🔵 **TÍCH HỢP** | Import vào analytics |
| `tca/benchmark.py` (161 LOC) | 🔵 **TÍCH HỢP** | Import vào analytics |
| `tca/slippage.py` (175 LOC) | 🔵 **TÍCH HỢP** | TCA-specific decomposition |
| `tca/tca_report.py` (143 LOC) | 🔵 **TÍCH HỢP** | Import vào reporting |

### 1.14 Binance Adapter → Canonical: `execution/brokers/binance.py`

| File | Hành động |
|------|-----------|
| `execution/brokers/binance.py` | ✅ **GIỮ LẠI** |
| `execution/exchange/binance_adapter.py` | 🔴 **XOÁ** |
| `execution/exchange/coinbase_adapter.py` | 🔴 **XOÁ** |
| `execution/adapters/binance_adapter.py` | 🔴 **XOÁ** |
| `execution/adapters/broker_bridge.py` | 🔴 **XOÁ** — stub `return {}` |

### 1.15 Orderbook → Canonical: `execution/orderbook_enhanced.py`

| File | Hành động |
|------|-----------|
| `execution/orderbook_enhanced.py` (437 LOC) | ✅ **GIỮ LẠI** |
| `execution/orderbook_core.py` (22 LOC) | 🔴 **XOÁ** — Minimal stub |
| `execution/orderbook_simulator.py` | ✅ **GIỮ LẠI** — Khác mục đích |
| `execution/benchmark_orderbook.py` | 🔴 **XOÁ** — Orphan + magic numbers |

---

## PHASE 2: ORPHAN INTEGRATION — Tích hợp file mồ côi có giá trị {#phase-2}

> **Mục tiêu**: Tận dụng tối đa code đã viết bằng cách nối chúng vào đúng chỗ.
> **Ước lượng**: 3-4 ngày

### 2.1 Orphans BẮT BUỘC TÍCH HỢP (Standash requirement)

| # | File Orphan | LOC | Import vào | Cách sử dụng cụ thể | Standash § |
|---|------------|-----|-----------|---------------------|-----------|
| 1 | `execution/order_id.py` | 102 | `execution/execution_engine.py` | `from qtrader.execution.order_id import OrderIdGenerator` → Gọi `generate()` khi tạo order | §4.7 |
| 2 | `execution/adverse_model.py` | 75 | `execution/smart_router.py` | `from qtrader.execution.adverse_model import AdverseSelectionModel` → Pre-trade check | §4.7 |
| 3 | `execution/microstructure/queue_model.py` | 111 | `execution/smart_router.py` | `from ...queue_model import QueueModel` → Tính queue position | §4.7 |
| 4 | `execution/microstructure/hidden_liquidity.py` | 79 | `execution/smart_router.py` | `from ...hidden_liquidity import HiddenLiquidityDetector` | §4.7 |
| 5 | `execution/microstructure/toxic_flow.py` | 80 | `execution/smart_router.py` | `from ...toxic_flow import ToxicFlowDetector` | §4.7 |
| 6 | `execution/microstructure/spread_model.py` | 97 | `execution/smart_router.py` | `from ...spread_model import SpreadModel` | §4.8 |
| 7 | `hft/spoofing.py` | - | `compliance/surveillance_engine.py` | `from qtrader.hft.spoofing import SpoofingDetector` | §4.7 |
| 8 | `execution/execution_quality.py` | 153 | `analytics/tca_engine.py` | `from ...execution_quality import ExecutionQualityMetrics` | §9 |
| 9 | `execution/degradation_handler.py` | 131 | `core/orchestrator.py` | `from ...degradation_handler import DegradationHandler` | §6 |
| 10 | `audit/compliance_exporter.py` | 145 | `audit/reporting_engine.py` | `from ...compliance_exporter import ComplianceExporter` | §5.3 |
| 11 | `audit/regulatory_export.py` | 135 | `audit/reporting_engine.py` | `from ...regulatory_export import RegulatoryExport` | §11.2 |
| 12 | `audit/trade_audit.py` | 117 | `oms/order_management_system.py` | `from qtrader.audit.trade_audit import TradeAuditor` → Log mỗi trade | §5.3 |
| 13 | `audit/replay_audit.py` | 155 | `verification/replay_validator.py` | `from ...replay_audit import ReplayAuditor` | §7.1 |
| 14 | `governance/model_risk.py` | 106 | `governance/approval_pipeline.py` | `from ...model_risk import ModelRiskScorer` | §8.1 |
| 15 | `governance/approval_pipeline.py` | 124 | `core/orchestrator.py` | `from ...approval_pipeline import ApprovalPipeline` | §8.1 |
| 16 | `oms/replay_engine.py` | 182 | `backtest/engine.py` | `from qtrader.oms.replay_engine import ReplayEngine` | §7.1 |
| 17 | `risk/regime_adapter.py` | - | `risk/realtime.py` | `from ...regime_adapter import RegimeRiskAdapter` | §4.6 |
| 18 | `backtest/l2_broker_sim.py` | 283 | `backtest/engine.py` | `from ...l2_broker_sim import L2BrokerSim` | §7.1 |
| 19 | `backtest/walk_forward_bt.py` | 150 | `research/session.py` | `from ...walk_forward_bt import WalkForwardBT` | ML |
| 20 | `portfolio/drawdown_controller.py` | - | `risk/realtime.py` | `from ...drawdown_controller import DrawdownController` | §4.6 |
| 21 | `core/event_validator.py` | - | `core/event_bus.py` | `from ...event_validator import EventValidator` | §7.2 |
| 22 | `core/event_bus_adapter.py` | - | `core/event_bus.py` | `from ...event_bus_adapter import EventBusAdapter` | Async |
| 23 | `execution/retry_handler.py` | - | `execution/execution_engine.py` | `from ...retry_handler import RetryHandler` (fix sleep first) | §4.7 |

### 2.2 Orphans GIỮ nhưng tích hợp SAU (future phases)

| # | File | Lý do giữ | Tích hợp khi nào |
|---|------|-----------|-----------------|
| 1 | `hft/market_maker.py` | MM strategy | Khi build MM |
| 2 | `backtest/tick_engine.py` (105 LOC) | Tick-level backtest | Khi cần HFT backtest |
| 3 | `backtest/multi_asset.py` (223 LOC) | Multi-asset | Khi scale |
| 4 | `execution/strategy/slicing.py` | Order slicing | Khi build TWAP/VWAP |
| 5 | `execution/strategy/scheduler.py` | Scheduler | Khi build scheduled execution |
| 6 | `execution/rl/reward.py` | RL reward | Khi train RL |
| 7 | `ml/model_comparator.py` | A/B testing | Khi model selection |
| 8 | `models/catboost_model.py` | CatBoost | Khi thêm model |
| 9 | `research/walkforward.py` | Research | Khi research flow |
| 10 | `pipeline/deployment.py` | Deployment | Khi CI/CD |

### 2.3 Meta Module — Đánh giá đặc biệt

| File | LOC | Quyết định | Tích hợp ở đâu |
|------|-----|-----------|----------------|
| `meta/genetic.py` | 177 | 🔵 **GIỮ + TÍCH HỢP** | `research/session.py` — Alpha discovery |
| `meta/self_evolution.py` | 149 | 🔵 **GIỮ + TÍCH HỢP** | `pipeline/research.py` — Parameter evolution |
| `meta/strategy_generator.py` | 100 | 🔵 **GIỮ + TÍCH HỢP** | `meta/genetic.py` chain |
| `meta/multi_agent.py` | 104 | 🟡 **GIỮ** — Future | Multi-agent portfolio |
| `meta/lifecycle_manager.py` | - | 🔵 **GIỮ + TÍCH HỢP** | `governance/approval_pipeline.py` |
| `meta/risk_filter.py` | - | 🔵 **GIỮ + TÍCH HỢP** | `meta/self_evolution.py` |
| `meta/shadow_enforcer.py` | - | 🔵 **GIỮ + TÍCH HỢP** | `governance/approval_pipeline.py` |
| `meta/approval_system.py` | - | 🔴 **XOÁ** — Trùng governance | - |
| `meta/governance_engine.py` | - | 🔴 **XOÁ** — Trùng governance | - |
| `meta/deployment_pipeline.py` | - | 🔴 **XOÁ** — Trùng pipeline | - |
| `meta/self_diagnostic.py` | - | 🟡 **GIỮ** — Future | Self-diagnostic |
| `meta/memory.py` | - | 🟡 **GIỮ** — Future | Experience replay |
| `meta/audit_logger.py` | - | 🔴 **XOÁ** — Trùng core/logger | - |
| `meta/constraint_engine.py` | - | 🔀 **HỢP NHẤT** vào `risk/limits.py` | - |

---

## PHASE 3: INFRASTRUCTURE WIRING — 6 Phase -1 Authority {#phase-3}

> **Nguồn**: audit_output.md — "Infrastructure-Integration Gap"
> **Ước lượng**: 3-4 ngày

### 3.1 SeedManager (D = 0.05 → Target >= 0.95)

**Hiện trạng**: Implemented nhưng 0 module import.

| Nơi tích hợp | Cách sử dụng |
|-------------|-------------|
| `core/orchestrator.py` `__init__()` | `self.seed_mgr = SeedManager.from_config(...)` then `self.seed_mgr.apply_global()` |
| `meta/genetic.py` | Thay `random.choice()` bằng `rng = numpy.random.default_rng(seed_mgr.get_module_seed("meta.genetic"))` |
| `meta/self_evolution.py` | Derive seed cho evolution |
| `meta/strategy_generator.py` | Derive seed |
| `ml/online_learning.py` | `rng = numpy.random.default_rng(seed_mgr.get_module_seed("ml.online"))` |
| `backtest/tearsheet.py` | Derived seed cho demo data |

### 3.2 DecimalAdapter (P = 0.63 → Target >= 0.95)

**Hiện trạng**: 1 importer duy nhất.

| Nơi tích hợp | Cách sử dụng |
|-------------|-------------|
| `execution/execution_engine.py` | `from qtrader.core.decimal_adapter import d` → `price = d(raw_price)` |
| `oms/order_management_system.py` | Tất cả price/qty qua `d()` |
| `risk/realtime.py` | VaR, drawdown, leverage dùng `Decimal` |
| `portfolio/` (all files) | NAV, cash, funding dùng `Decimal` |
| `analytics/accounting.py` | PnL dùng `Decimal` |
| `analytics/fee_engine.py` | Fee calculation dùng `Decimal` |
| `core/state_store.py` | Equity, positions as `Decimal` |

### 3.3 AsyncAdapter (A = 0.80 → Target >= 0.95)

**Hiện trạng**: 0 importer.

| Nơi tích hợp | Cách sử dụng |
|-------------|-------------|
| `execution/brokers/binance.py` | `session = await async_authority.get_session()` |
| `data/market/coinbase_market.py` | Thay `time.sleep()` bằng async rate limiter |
| `data/pipeline/sources/coinbase.py` | Shared session |
| `core/orchestrator.py` | Init at boot, cleanup at shutdown |

### 3.4 FailFastEngine (F = 0.38 → Target >= 0.90)

**Hiện trạng**: 1 importer.

| Nơi tích hợp | Cách sử dụng |
|-------------|-------------|
| `core/orchestrator.py` | `self.fail_fast = FailFastEngine(self.global_orchestrator)` |
| `execution/execution_engine.py` | `except Exception as e: await self.fail_fast.handle_error("execution", e)` |
| `oms/order_management_system.py` | OMS errors → fail_fast |
| `risk/realtime.py` | Risk breach → fail_fast |
| `data/market/` | Connection errors → fail_fast |

### 3.5 TraceManager + QTraderLogger (O = 0.21 → Target >= 0.85)

| Nơi tích hợp | Cách sử dụng |
|-------------|-------------|
| **MỌI module** | `from qtrader.core.logger import log_event` |
| `core/orchestrator.py` | `TraceManager.start_trace()` tại mỗi market event lifecycle |
| `execution/` | `log_event("execution", "order_submit", ...)` |
| `oms/` | `log_event("oms", "state_transition", ...)` |
| `risk/` | `log_event("risk", "check_passed/failed", ...)` |

### 3.6 ConfigEnforcer + LatencyMonitor + PrecisionValidator

| Authority | Nơi tích hợp | Cách sử dụng |
|-----------|-------------|-------------|
| `ConfigEnforcer` | `main.py` startup | `enforce_compliance(strict=True)` |
| `LatencyMonitor` | `core/orchestrator.py` | `start_stage()` / `end_stage()` per pipeline stage |
| `PrecisionValidator` | `execution/`, `oms/` | `validate(price, "oms.price")` at boundaries |

---

## PHASE 4: STUB COMPLETION {#phase-4}

> **Ước lượng**: 2-3 ngày

| File | Method | Hiện tại | Cần làm |
|------|--------|---------|---------|
| `execution/execution_engine.py:77` | method 1 | `return {}` | Implement routing via `smart_router.py` |
| `execution/execution_engine.py:81` | method 2 | `return {}` | Implement fill handling |
| `execution/execution_engine.py:85` | method 3 | `return {}` | Implement state update |
| `execution/routing/router.py:57` | `route()` | `return {}` | Multi-venue routing |
| `execution/routing/fill_model.py:50` | `predict()` | `return {}` | Fill probability model |
| `execution/routing/cost_model.py:55` | `estimate()` | `return {}` | Cost estimation |
| `execution/routing/liquidity_model.py:48` | `assess()` | `return {}` | Liquidity assessment |
| `analytics/performance.py` | `calculate_sharpe` | `return 2.1` | Real Sharpe ratio |
| `execution/router.py` | `calculate_fill_prob` | `return 0.85` | Real fill probability |

---

## PHASE 5: DEAD CODE REMOVAL {#phase-5}

> **Ước lượng**: 1 ngày
> **CHỈ THỰC HIỆN SAU KHI Phase 1-2 merge hoàn tất**

### Files xoá ngay (duplicate orphans)

```
governance/kill_switch.py
meta/orchestrator.py
system/system_orchestrator.py
system/pipeline_validator.py
execution/order_fsm.py
execution/reconciliation_service.py
execution/exchange/binance_adapter.py
execution/exchange/coinbase_adapter.py
execution/adapters/binance_adapter.py
execution/adapters/broker_bridge.py
execution/rl_agent.py
hft/rl_agent.py
hft/microprice.py
hft/imbalance.py
hft/queue_model.py
hft/toxic_flow.py
execution/orderbook_core.py
execution/benchmark_orderbook.py
meta/approval_system.py
meta/governance_engine.py
meta/deployment_pipeline.py
meta/audit_logger.py
meta/capital_allocator.py
portfolio/reallocator.py
portfolio/position_sizing.py
risk/portfolio/accounting.py
risk/portfolio/fees.py
```

**Tổng: ~27 files xoá ngay**

### Files xoá SAU merge

```
portfolio/allocator.py               → merged vào risk/portfolio/allocator.py
risk/portfolio/capital_allocator.py  → merged
risk/portfolio_allocator_enhanced.py → merged
portfolio/fee_engine.py              → merged vào analytics/fee_engine.py
portfolio/nav_engine.py              → merged vào analytics/accounting.py
portfolio/cash_ledger.py             → merged
portfolio/funding_engine.py          → merged
execution/slippage_control.py        → merged
execution/routing/cost_model.py      → merged
ml/regime_detector.py                → merged vào ml/regime.py
ml/hmm_regime.py                     → merged
risk/portfolio/sizing.py             → merged
risk/position_sizer.py               → merged
risk/network_kill_switch.py          → merged
meta/constraint_engine.py            → merged vào risk/limits.py
```

**Tổng thêm: ~15 files sau merge**

---

## PHASE 6: DEEP DISCIPLINE FIX {#phase-6}

> **Ước lượng**: 3-5 ngày

### 6.1 Blocking IO

| File | Fix |
|------|-----|
| `data/market/coinbase_market.py:136,140` | `time.sleep()` → async rate limiter |
| `execution/retry_handler.py:36` | `asyncio.sleep()` → event-driven backoff |
| `execution/reconciliation_engine.py:44` | `asyncio.sleep(0.1)` → condition wait |
| `core/event_store.py:74,117,152,190` | `open()` → `aiofiles.open()` |

### 6.2 State Management

| File | Fix |
|------|-----|
| `core/state_store.py` | 16x `deepcopy()` → immutable dataclass + copy-on-write |
| `core/state_store.py:134` | Unbounded append → windowed buffer |
| `core/event_bus.py:70` | Unbounded tasks → periodic cleanup |

### 6.3 Concurrency

| Fix |
|-----|
| Add `asyncio.Lock()` cho shared state trong `state_store.py`, `oms/` |
| Unify: dùng `asyncio.Lock` cho tất cả async code |

---

## PHASE 7: INTEGRATION TEST {#phase-7}

> **Ước lượng**: 2-3 ngày

### Critical Path Validation

```
Market Feed → Data Quality Gate → Feature Factory → Alpha Signal
    → Risk Pre-Gate → Portfolio Allocator → Smart Order Router
    → Exchange Adapter → Fill Event → Reconciliation → PnL
```

### Verification Commands

```bash
ruff check qtrader/ tests/
mypy qtrader/ --strict
pytest tests/ --cov=qtrader --cov-fail-under=90
cd rust_core && cargo test
```

---

## TÓM TẮT

| Phase | Mục tiêu | Files | Ước lượng |
|-------|---------|-------|-----------|
| **0** | Tạo 15 `__init__.py` | 15 | 30 phút |
| **1** | Hợp nhất 18 cụm trùng lặp | ~45 | 2-3 ngày |
| **2** | Tích hợp ~23 orphans có giá trị | ~23 | 3-4 ngày |
| **3** | Wire 6 infrastructure authority | ~30 modules | 3-4 ngày |
| **4** | Hoàn thiện 9 stub methods | ~6 | 2-3 ngày |
| **5** | Xoá ~42 dead files | ~42 | 1 ngày |
| **6** | Fix blocking IO, deepcopy, concurrency | ~10 | 3-5 ngày |
| **7** | Integration test | All | 2-3 ngày |
| **TOTAL** | | | **~17-23 ngày** |

### Target Scores

| Dimension | Hiện tại | Target |
|-----------|---------|--------|
| Determinism | 0.05 | >= 0.95 |
| Failure Transparency | 0.38 | >= 0.90 |
| Config Authority | 0.66 | >= 0.90 |
| Numeric Precision | 0.63 | >= 0.95 |
| Async Discipline | 0.80 | >= 0.95 |
| Observability | 0.21 | >= 0.85 |
| **Overall** | **0.46** | **>= 0.92** |

> [!IMPORTANT]
> **Thứ tự PHẢI tuân thủ**: Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7

> [!CAUTION]
> **KHÔNG XOÁ FILE TRƯỚC KHI HỢP NHẤT**. Phase 5 chỉ thực thi SAU Phase 1-2 hoàn tất.
