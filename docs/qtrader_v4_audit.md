# Kiểm toán Toàn diện QTrader v4 (Senior Quant + Systems)

Ngày: 2026-03-13

Phạm vi: Repo `qtrader/` (Python 3.10), `rust_core/` (PyO3) và phần triển khai (`Dockerfile`, `docker-compose.yml`, `.dockerignore`).

Trọng tâm kiểm toán:
- Hiệu quả cấu trúc & khả năng mở rộng (mức độ mô-đun hóa, cầu nối Python-Rust, triển khai trên Apple Silicon / ARM64)
- Logic định lượng & alpha (tối ưu EV: phát hiện chế độ thị trường, xoay vòng mô hình, cấu trúc hóa rủi ro/portfolio)
- Độ trung thực khớp lệnh (mô phỏng L2, tính hiện thực của SOR, mô hình trượt giá/độ trễ)
- An toàn & rào chắn (Nano-safety, kill switch thời gian thực, budget circuit breaker)

## Tóm tắt điều hành

QTrader v4 có bố cục package khá rõ (data / features / ml / execution / risk), nhưng đường chạy runtime quan trọng chưa sẵn sàng cho production:
- Nhiều module lõi bị lỗi import hoặc lệch interface (typing của EventBus, DB/MLflow/DuckDB client, broker adapters).
- Execution fidelity chủ yếu là placeholder (logic fill của L2 simulator chưa có; SOR không nhận biết orderbook).
- Rust kernel có tồn tại nhưng chưa được tích hợp vào runtime Python; tuyên bố “zero-copy” hiện không đúng với binding hiện tại.
- Logic quant (GMM regimes, rotation, bộ phân bổ rủi ro) phần lớn mới ở mức khung, thiếu guardrail cho EV và thiếu hoàn thiện toán rủi ro.

Kết luận: v4 hiện phù hợp mô tả là “khung framework + demo”, chưa phải hệ thống giao dịch mức tổ chức (institutional-grade) ở thời điểm này.

## Phương pháp & giới hạn

Đã thực hiện:
- Kiểm toán tĩnh code, tìm có mục tiêu ở các mảng: biên PyO3, chuyển Polars->NumPy, regime/rotation, HRP/CVaR/Kelly, L2/SOR, và guardrail.
- Đối chiếu wiring module từ `scripts/live_engine.py` và mô hình sự kiện (`qtrader/core/event.py`).

Giới hạn trong quá trình kiểm chứng:
- Môi trường local `python3` là Apple system Python 3.9.6, không tương thích với một phần code v4 (ví dụ dataclasses `kw_only`). Repo mục tiêu Python 3.10 (`pyproject.toml:9`).
- Đã bổ sung bộ smoke/contract tests tối thiểu trong `tests/` để đảm bảo các module “đường chạy quan trọng” import được và các hành vi cơ bản (SOR, L2 crossing/depletion) hoạt động đúng dưới Python 3.10.

## Lỗ hổng nghiêm trọng (Kiến trúc hoặc Logic)

Tình trạng hiện tại (sau hotfix 2026-03-13):
- (1) EventBus: **Đã khắc phục + nâng cấp v4.1** (backpressure, metrics, shutdown sạch).
- (2) Broker contracts + OMS: **Đã khắc phục + live REST tối thiểu** (Coinbase JWT + Binance fills; có wiring market_state).
- (3) L2 sim + SOR: **Đã nâng cấp v4.3** (queue price‑time, partial fills theo trade prints, SOR theo impact).
- (4) MLflow registry: **Đã khắc phục + guardrail** (fail-fast tracking/experiment; log theo flavor + metadata).
- (5) DuckDB client: **Đã khắc phục + I/O guard** (validate path/URI, có close()).
- (6) Rust kernel: **Đã giảm thiểu + wired** (feature microstructure trong market_state; có fallback nếu chưa build).
- (7) Tooling drift: **Đã khắc phục + dọn lint bước 1** (tooling target khớp Python 3.10; lint còn cần chạy CI để xác nhận).

### 1) Vỡ runtime lõi

- **EventBus không import được (NameError)**:
  - Tình trạng trước đây: `qtrader/core/bus.py` dùng `Any` trong typing nhưng không import, gây `NameError`.
  - Tình trạng hiện tại: **Đã sửa + nâng cấp v4.1**:
    - Import `Any` và `asyncio.gather(..., return_exceptions=True)` để một handler lỗi không làm sập bus.
    - **Backpressure** (queue bounded), **metrics** (counters, queue depth, latency), **shutdown sạch** với sentinel.
  - Tác động còn lại: FIFO tuyệt đối vẫn được giữ; chưa có worker‑pool hoặc backpressure theo event type (đã chủ động chọn kiến trúc FIFO).

### 2) Lệch hợp đồng giữa Broker Adapters và OMS/SOR

- **OMS kỳ vọng `BrokerAdapter.submit_order()` và `get_balance()`**:
  - Tình trạng hiện tại: OMS vẫn gọi `submit_order/get_balance`, đã thêm **market_state cache** và **pending order context** để phục vụ SOR/impact.

- **Adapter Coinbase không triển khai đúng Protocol**:
  - Tình trạng hiện tại: **Đã sửa + live REST tối thiểu**.
    - Coinbase adapter đã triển khai đúng `submit_order/cancel_order/get_fills/get_balance` (simulate có fill nội bộ).
    - **Live REST** dùng **CDP Key/JWT** (create/cancel/order fills/balance) với timeout + retry/backoff.
  - Tác động còn lại: Live REST mới là mức tối thiểu; chưa có websocket private channels.

- **Adapter Binance lệch chữ ký hàm so với Protocol và thiếu import**:
  - Tình trạng hiện tại: **Đã sửa + fills thật**.
    - Chữ ký khớp Protocol, đã bổ sung import thiếu.
    - `get_fills(order_id)` gọi `myTrades` và chuyển thành `FillEvent`.
  - Tác động còn lại: mapping `order_id -> symbol` vẫn là in‑memory; nếu restart trong live, cancel/fills cho order cũ có thể fail-safe.

- **Market state wiring cho SOR**:
  - Tình trạng hiện tại: **Đã có MarketStateUpdater** subscribe `MARKET_DATA` để cập nhật OMS market_state; source Coinbase pipeline emit đúng schema.
  - Tác động còn lại: các nguồn dữ liệu khác cần chuẩn hóa schema `bid/ask/bid_size/ask_size` và `venue`.

### 3) Độ trung thực khớp lệnh chưa đạt chuẩn institutional

- **Mô phỏng hàng đợi L2 không fill**:
  - Tình trạng hiện tại: **Đã nâng cấp**.
    - Queue **price‑time priority** theo side.
    - **Partial fills** theo trade prints; hỗ trợ queue depletion và crossing fills.
  - Tác động còn lại: vẫn là mô phỏng heuristic theo top‑of‑book; chưa có depth curve đầy đủ hoặc latency distribution thực tế.

- **SOR không nhận biết orderbook**:
  - Tình trạng hiện tại: **Đã nâng cấp**.
    - SOR chọn venue theo **expected execution cost** (price + impact) dựa trên `MarketImpactModel`.
    - Tie‑break theo depth; fallback theo balance nếu thiếu market_state.
  - Tác động còn lại: impact model vẫn đơn giản; chưa dùng depth curve/latency phân phối.

### 4) MLflow Registry không hoạt động

- Tình trạng hiện tại: **Đã sửa + guardrail**:
  - Fail‑fast nếu `set_tracking_uri`/`set_experiment` lỗi.
  - Log model theo flavor (sklearn/xgboost/catboost/lightgbm) + metadata (model type, params hash, timestamp).
  - Có `artifact_path` và `register_model_name` tùy chọn.
- Tác động còn lại: “log theo flavor” vẫn phụ thuộc môi trường cài đặt; model type lạ sẽ rơi về `model_summary.txt` (best‑effort).

### 5) DuckDB Client không hoạt động

- Tình trạng hiện tại: **Đã sửa + guard I/O**:
  - Import đầy đủ `duckdb`/`polars`.
  - Validate path/URI trước khi query; có `close()` tránh leak.
  - Dependency đã bổ sung trong `pyproject.toml`.
- Tác động còn lại: cần Parquet hợp lệ và quyền truy cập đường dẫn/URI tương ứng.

### 6) Rust Kernel chưa được tích hợp (và tuyên bố “Zero-copy” là sai)

- Tình trạng hiện tại: **Đã giảm thiểu + wired**:
  - Đã chỉnh comment để không claim sai “zero-copy” khi trả `Vec<f64>` (`rust_core/src/lib.rs` phần `compute_microstructure_features`).
  - Đã thêm wrapper `qtrader/execution/orderbook_core.py` để import `qtrader_core` thân thiện và báo lỗi hướng dẫn build.
  - Đã bổ sung targets `rust-py`/`rust-py-dev` trong `Makefile` để build/install bằng `maturin`.
  - Đã **wire** vào `MarketStateUpdater` để enrich `micro_*` features (spread/imbalance/mid) theo symbol/venue.
- Tác động còn lại: Rust core chưa đi vào execution path sâu (alpha/strategy vẫn cần chủ động dùng `micro_*`), và đường trả dữ liệu vẫn là copy‑to‑Python (chưa zero‑copy).

### 7) Trôi cấu hình tooling làm tăng rủi ro production

- Tình trạng hiện tại: **Đã sửa** để tooling khớp Python 3.10:
  - Ruff target-version: `pyproject.toml:47-50`
  - Mypy python_version: `pyproject.toml:55-58`
- Tình trạng hiện tại (v4.4): **Đã dọn lint bước 1** (formatting + loại bỏ lỗi cơ bản).
- Tác động còn lại: cần chạy `ruff`/`mypy` trong CI để xác nhận sạch toàn bộ; còn khả năng tồn đọng lint ở legacy modules.

## Cơ hội tối ưu (Hiệu năng hoặc cải thiện EV)

### A) Hiệu quả cấu trúc & khả năng mở rộng

- **Chuẩn hóa một “hợp đồng engine” duy nhất**:
  - Hiện tại `scripts/live_engine.py` chưa được nối vào Alpha/Strategy/Risk/Execution; chủ yếu là health check và stats giả (`scripts/live_engine.py:33-92`).
  - Triển khai pipeline thật: `MarketDataEvent -> AlphaModel -> SignalEvent -> Strategy -> OrderEvent -> Risk -> Execution -> FillEvent`.
  - Lợi ích: tái lập, unit test, quan sát production.

- **Làm Protocol “có thể cưỡng chế”**:
  - Biến Protocol thành abstract base class rõ ràng hoặc runtime checks lúc startup (fail-fast).
  - Lợi ích: “một adapter hỏng” không âm thầm làm sai execution.

### B) Cầu nối Python-Rust (PyO3) & luồng dữ liệu

- **Batch L2 updates và trích xuất feature**:
  - API Rust hiện tại `apply_l2_update(side, price, qty)` xử lý từng update (`rust_core/src/lib.rs:46-63`).
  - Thêm phương thức ingest mảng (side/price/qty) theo batch để giảm overhead call từ Python.

- **Trả về Arrow/NumPy view (zero-copy thật)**:
  - Thay `Vec<f64>` bằng `PyArray1<f64>` (crate `numpy`) hoặc Arrow buffer.
  - Lợi ích: tránh cấp phát/copy mỗi tick.

- **Tránh vòng Polars->Pandas**:
  - HRP/mean-variance dùng `returns.to_pandas().cov()` và `.corr()` (`qtrader/portfolio/hrp.py:20-21`, `qtrader/portfolio/optimization.py:34`).
  - Giữ nhất quán “miền bộ nhớ” (Polars -> NumPy) và tính cov/corr bằng NumPy/BLAS.
  - Lợi ích: giảm áp lực bộ nhớ, ít copy, mở rộng tốt hơn với universe lớn.

### C) Quant EV: Regime Detection & Rotation

- **Regime model cần hiệu chỉnh & guardrail**:
  - GMM chạy trên feature thô với `np.nan_to_num` (`qtrader/ml/regime.py:23-26`, `qtrader/ml/regime.py:35-37`).
  - Thêm scaling feature, rolling refit, và kiểm định out-of-sample (forward returns theo regime).
  - Lợi ích: regime label mang tính dự báo thay vì mô tả.

- **Rotation cần “cổng” hiệu năng**:
  - `ModelRotator` xoay dựa trên mapping regime ID (`qtrader/ml/rotation.py:16-29`).
  - `RotationHysteresis` có sẵn (`qtrader/ml/stability.py:7-52`) nhưng không dùng trong `AutonomousLoop` (`qtrader/ml/autonomous.py:25-38`).
  - Thêm gating: “chỉ rotate nếu uplift kỳ vọng > chi phí chuyển + bất định”, kèm cooldown/persistence.
  - Lợi ích: giảm whipsaw, EV ổn định hơn.

### D) Rủi ro: Win Rate vs Risk/Reward & bảo vệ tail

- **HRP triển khai chưa đúng (placeholder)**:
  - Code đưa thẳng ma trận khoảng cách vuông vào `linkage()` (`qtrader/portfolio/hrp.py:24-26`) và trả weight inverse-variance (`qtrader/portfolio/hrp.py:33-36`).
  - Cần triển khai quasi-diagonalization và recursive bisection đúng chuẩn; dùng condensed distance vector.

- **CVaR optimizer đang là stub**:
  - `qtrader/portfolio/hrp.py:38-47` trả equal weights.
  - Tail control mức tổ chức cần: mô hình hóa PnL theo kịch bản, constraint, turnover limit, leverage/margin, stress test.

- **Runtime risk không cập nhật state**:
  - `RuntimeRiskEngine` kiểm `current_drawdown/current_exposure` nhưng không có nơi cập nhật trong repo (`qtrader/risk/runtime.py:7-27`).
  - Nối exposure từ OMS (`qtrader/execution/oms.py:32-38`) và equity curve từ backtest/live PnL.

- **Kelly sizing thiếu an toàn**:
  - `qtrader/portfolio/sizing.py:7-14` tính Kelly rồi chặn dưới 0, nhưng không cap phía trên và không xử lý `win_loss_ratio == 0`.
  - Chuẩn tổ chức: luôn cap (max leverage/max notional), dùng half/quarter Kelly, và ước lượng input từ phân phối hậu nghiệm (posterior), không dùng point estimate.

### E) Execution fidelity: Trượt giá & độ trễ trên M4

- **L2 simulator phải có trade, queue depletion, partial fill**:
  - Hoàn thiện `qtrader/backtest/l2_broker_sim.py:59-62` dựa trên trade events, price-time priority, và “volume ahead” depletion.
  - Thêm latency distribution (không sleep cố định), và áp `MarketImpactModel` (`qtrader/backtest/impact.py:6-44`) vào giá fill.

- **SOR nên tối ưu expected shortfall khi thực thi**:
  - Tính xác suất fill và trượt giá dựa trên depth curve; route theo expected execution cost tốt nhất, không theo balance (`qtrader/execution/sor.py:13-29`).

## Kiểm toán triển khai (Docker, ARM64, kích thước context)

- **Image không pin phiên bản**:
  - `docker-compose.yml:15` dùng `timescale/timescaledb:latest-pg16` và `docker-compose.yml:27` dùng `ghcr.io/mlflow/mlflow:latest`.
  - Chuẩn tổ chức: pin version và (nếu có) digest; ghi vào release notes.

- **Cấu hình network có thể fail trên máy mới**:
  - `docker-compose.yml:36-38` khai báo external network `sanauto-production-net` nhưng service không attach vào; ngoài ra external network cần tạo trước.
  - Dễ gặp lỗi “network not found” trên môi trường sạch.

- **Kiến trúc container `app` bị mơ hồ**:
  - README nói app layer chạy `linux/amd64` dưới Rosetta, nhưng `docker-compose.yml` không set `platform` cho `app`.
  - `Dockerfile` có comment về Rosetta (`Dockerfile:16-17`) nhưng không set platform hoặc xử lý multi-arch build.
  - Cần quyết định: app ARM64 thật (ưu tiên) hay amd64 emulation (chỉ khi dependency bắt buộc).

- **Build context lớn; bind-mount làm mất tính tái lập**:
  - Repo nặng do `rust_core/target` tồn tại local (~719MB). `.dockerignore` đã loại (`.dockerignore:7`), nhưng `docker-compose.yml:6-7` mount toàn bộ repo vào container, làm mất cô lập và tính tái lập cho chạy “prod-like”.

## Đánh giá Guardrails (Nano-Safety + Budget Circuit Breakers)

- **SafetyLayer cơ bản nhưng chưa đạt chuẩn institutional**:
  - Có rate limit, ngưỡng spread, và min depth (`qtrader/execution/safety.py:12-45`).
  - Thiếu: cơ chế “flatten all” cưỡng chế, kill switch theo symbol, rate limit theo venue, phát hiện bất thường có trạng thái (stateful), và quy trình phục hồi sau halt.

- **Budget circuit breaker hiện là stub (chỉ log)**:
  - `qtrader/analytics/budget.py:21-25` chỉ set cờ throttle và không tích hợp Ray/K8s.
  - Chuẩn tổ chức: job admission control, preflight cost, kill policy có audit log.

## Chấm điểm định lượng (1–10)

- Mô-đun hóa: **4/10**
  - Bố cục sạch, nhưng interface chưa khớp và wiring engine chưa đầy đủ.
- Độ trung thực khớp lệnh: **2/10**
  - L2 sim thiếu fill logic, SOR không orderbook-aware, adapters bị lỗi.
- “Risk Hardware” (Bảo vệ tail + Guardrails): **3/10**
  - Có khung guardrail, nhưng toán rủi ro (CVaR/HRP) là placeholder và runtime risk không nhận state thật.

## Lộ trình hành động (v5)

Ưu tiên: “an toàn & đúng trước, sau đó EV, rồi mới đến scale”.

1. **Làm tất cả module import-clean dưới Python 3.10**:
   - Sửa thiếu import và lệch Protocol (EventBus, DuckDBClient, ModelRegistry, broker adapters).
2. **Ổn định interface**:
   - Một hợp đồng `BrokerAdapter` duy nhất; enforce lúc startup.
   - OMS/SOR chỉ dùng adapters qua hợp đồng này.
3. **Triển khai wiring engine thật**:
   - Thay loop mock trong `scripts/live_engine.py` bằng pipeline chạy theo events và state của component.
4. **Nâng độ hiện thực execution**:
   - Hoàn thiện L2 fill logic + thêm trade events; tích hợp impact model; latency distribution thực tế.
   - Thay SOR “balance-based” bằng router dựa trên depth/impact.
5. **Gia cố risk**:
   - HRP đúng chuẩn; CVaR/ES thật; enforce constraint leverage/exposure/turnover.
   - Nối drawdown/exposure runtime vào state thật (OMS + PnL).
6. **Guardrail cho EV ở regime/rotation**:
   - Rolling refit regime model; scale features; áp hysteresis vào AutonomousLoop.
   - Thêm cổng chuyển model dựa trên uplift out-of-sample sau khi trừ cost và bất định.
7. **Tích hợp Rust kernel**:
   - Đóng gói Rust với pipeline build chuẩn (ví dụ maturin) và tích hợp vào đường chạy feature/execution.
   - Thêm batch APIs và zero-copy thật (NumPy/Arrow).
8. **Tái lập deployment**:
   - Pin container versions; chốt platform của app; bỏ bind-mount trong compose “production”; đảm bảo network nội bộ hoặc tạo trước.
9. **Testing & CI**:
   - Thêm import tests + interface tests + 1 bài backtest/sim deterministic.
   - Thêm “smoke engine” test chạy end-to-end event flow.

## Phụ lục: Bản đồ file quan trọng

- Live loop / monitoring: `scripts/live_engine.py`, `qtrader/api/api.py`
- Event model + bus: `qtrader/core/event.py`, `qtrader/core/bus.py`
- Regime/rotation: `qtrader/ml/regime.py`, `qtrader/ml/rotation.py`, `qtrader/ml/stability.py`, `qtrader/ml/autonomous.py`
- Risk/portfolio: `qtrader/portfolio/optimization.py`, `qtrader/portfolio/hrp.py`, `qtrader/portfolio/sizing.py`, `qtrader/risk/runtime.py`
- Execution: `qtrader/execution/oms.py`, `qtrader/execution/sor.py`, `qtrader/execution/safety.py`, `qtrader/execution/brokers/*`
- Backtest execution: `qtrader/backtest/broker_sim.py`, `qtrader/backtest/l2_broker_sim.py`, `qtrader/backtest/impact.py`, `qtrader/backtest/engine_vectorized.py`
- Rust core: `rust_core/src/lib.rs`, `rust_core/Cargo.toml`
- Deployment: `Dockerfile`, `.dockerignore`, `docker-compose.yml`
