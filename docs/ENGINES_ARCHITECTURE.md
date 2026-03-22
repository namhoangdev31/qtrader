# QTrader Engines Architecture & Workflow

Tài liệu này tổng hợp toàn bộ các **Engine (Động cơ xử lý)** đang được định nghĩa trong hệ thống QTrader, bao gồm trạng thái kết nối (Connected/Disconnected), file/class liên quan, và phân tích chi tiết luồng tương tác (Workflow) của các engine đã được tích hợp.

---

## 1. Nhóm Khớp Lệnh & Mô Phỏng (Execution & Backtest Layer)

### 1.1. VectorizedEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `backtest/engine_vectorized.py`
- **Mục đích:** Tối ưu hóa tốc độ backtest cho các chiến lược thông qua việc sử dụng thư viện xử lý mảng tốc độ cao (như Polars/Pandas). Giải quyết bài toán backtest khối lượng dữ liệu lớn trong khâu Research.
- **Workflow & Tương tác:**
  - Instantiated tại: `research/session.py` và `backtest/walk_forward_bt.py`.
  - Được `ResearchSession` gọi tới khi người dùng yêu cầu chạy một bài test diện rộng trên historical data tĩnh.
  - Hàm/Method chính: Chạy thuật toán mô phỏng lệnh vector, trả về kết quả Portfolio performance ngay lập tức.

### 1.2. BacktestEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `backtest/engine.py`
- **Mục đích:** Động cơ backtest theo cơ chế sự kiện (Event-driven) truyền thống. Khớp lệnh tick-by-tick hoặc bar-by-bar để lập lập môi trường Live một cách chính xác nhất.
- **Workflow & Tương tác:**
  - Instantiated tại: internal trong module `backtest`.
  - Xử lý các Event Loop: nhận `TickEvent` / `BarEvent`, đẩy qua Strategy, sinh ra `OrderEvent`, và tự động khớp lệnh sinh ra `FillEvent`.

### 1.3. RustTickEngine (đi kèm TickEngineConfig)
- **Trạng thái:** ĐANG KẾT NỐI (Connected - tích hợp một phần)
- **File:** `backtest/tick_engine.py`
- **Mục đích:** Engine mô phỏng tick-level với độ trễ siêu thấp thông qua việc bind với thư viện Rust. Chuyên phục vụ cho High Frequency Trading hoặc Market Making evaluation.
- **Workflow & Tương tác:**
  - Config được tạo bởi `TickEngineConfig`.
  - `RustTickEngine` có thể nhận load trực tiếp các LOB (Limit Order Book) snapshots và tính toán trượt giá (slippage) micro-second.

### 1.4. PaperTradingEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `execution/paper_engine.py`
- **Mục đích:** Cho phép chiến lược chạy Forward-testing với tín hiệu Live Market nhưng không đẩy lệnh lên sàn (Fake execution).
- **Workflow & Tương tác:**
  - Instantiated tại: `research/session.py`.
  - Cung cấp môi trường dry-run an toàn bằng cách lắng nghe qua WebSocket/API tĩnh, cập nhật PnL giả lập.

### 1.5. ExecutionEngine
- **Trạng thái:** CHỜ KẾT NỐI NHIỀU HƠN / PLUGGABLE (Disconnected from main orchestrator but available)
- **File:** `execution/execution_engine.py`
- **Mục đích:** Engine chính dùng để gửi lệnh HTTP/FIX API tới các sàn giao dịch thật (Execution Layer).
- **Lý do chưa kết nối toàn diện:** Orchestrator hiện tại sử dụng interface để inject thay vì hardcode, do đó `ExecutionEngine` hoặc các adapter của nó thường được khởi tạo bởi DI (Dependency Injection) lúc run file main thay vì khởi tạo trực tiếp trong pipeline base.
- **Tương tác mong đợi:** Nhận `OrderEvent` từ `TradingOrchestrator`, xử lý route lệnh tới các sàn (Binance, Coinbase...), lắng nghe Webhook trả về `FillEvent`.

### 1.6. ShadowEngine
- **Trạng thái:** CHƯA KẾT NỐI (Disconnected / Standby)
- **File:** `execution/shadow_engine.py`
- **Mục đích:** Chạy song song (Shadow execution) với hệ thống thật. Sinh ra lệnh nhưng Drop trên đường mạng.
- **Lý do:** Đây là một tính năng nâng cao (A/B testing chiến lược trên Live Market) đang trong giai đoạn blueprint, chưa được gọi trực tiếp bằng Orchestrator.

---

## 2. Nhóm Tín Hiệu & Pipeline (Signal & Pipeline)

### 2.1. FactorEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `features/engine.py`
- **Mục đích:** Tính toán hàng loạt (Batch compute) và lưu trữ các Feature (đặc trưng dữ liệu), giảm tải việc tính toán lặp lại trong quá trình Backtest/Research.
- **Workflow & Tương tác:**
  - Được dùng trong `pipeline/research.py` để tiền xử lý `sym_df`.
  - Methods nổi bật: `compute()`, `get_all_feature_names()`.
  - Dữ liệu Feature sinh ra sẽ được nạp thẳng vào `AlphaEngine`.

### 2.2. AlphaEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `alpha/registry.py`
- **Mục đích:** Registry và Executor gộp cho nhiều file Alpha. Nó tổng hợp nhiều tín hiệu Alpha và đánh trọng số bằng Information Coefficient (IC) để tối ưu độ nhiễu.
- **Workflow & Tương tác:**
  - Được Pipeline (`research.py`) khởi tạo.
  - Methods nổi bật: `compute_all()`, `update_ic()`.
  - Liên tục cập nhật IC khi có PnL (thông qua returns của kỳ trước) để tự động de-weight các Alpha hoạt động kém.

### 2.3. CandleAlphaEngine
- **Trạng thái:** ĐANG KẾT NỐI (dưới dạng sub-class AlphaBase)
- **File:** `strategy/alpha/candle_patterns_alpha.py`
- **Mục đích:** Extract các Candlestick Patterns chuyên sâu.
- **Tương tác:** Đóng vai trò là một plugin trong `AlphaEngine`. Maintains một buffer dữ liệu nội bộ.

---

## 3. Nhóm ML & Thích Nghi (Learning & Adaptation)

### 3.1. MetaLearningEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `ml/meta_learning_engine.py`
- **Mục đích:** Online Machine Learning giúp nhận diện Regime thị trường (Bull/Bear/Crab) và điều chỉnh linh hoạt Weight của chuỗi các Strategy.
- **Workflow & Tương tác:**
  - Gắn trực tiếp vào `EnsembleStrategy` (`strategy/ensemble_strategy.py`).
  - Lắng nghe `regime_prob` qua method `update_regime_info()`.
  - Cung cấp `get_weights()` giúp `EnsembleStrategy` phân bổ tỷ trọng lệnh giữa các Sub-strategies dựa vào bối cảnh Live.

### 3.2. FeedbackEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `feedback/feedback_engine.py`
- **Mục đích:** "Bộ Não" học từ kinh nghiệm. Nhận chi tiết từng giao dịch khớp (Fills), phân tích sự chênh lệch (Slippage, Cost) để bù đắp điểm yếu.
- **Workflow & Tương tác:**
  - Khởi tạo tại `Tracking/TradingOrchestrator` (`core/orchestrator.py`).
  - Khi hệ thống có `fill_data`, Orchestrator truyền data đó cho `FeedbackEngine`.
  - Thông qua EventBus, FeedbackEngine gửi tín hiệu Reinforcement Learning ngược về cho `MetaLearningEngine` để rút kinh nghiệm.

### 3.3. LiveFeedbackEngine
- **Trạng thái:** CHƯA KẾT NỐI (Standby / Overlapped)
- **File:** `feedback/live_feedback_engine.py`
- **Mục đích:** Tương tự FeedbackEngine nhưng customize riêng cho streaming Live. Hiện tại `FeedbackEngine` chung dường như đang wrap xử lý toàn bộ nhu cầu của Orchestrator.

---

## 4. Nhóm Quản Trị Rủi Ro (Risk Management)

### 4.1. RuntimeRiskEngine
- **Trạng thái:** ĐANG KẾT NỐI (Connected)
- **File:** `risk/runtime.py` (và bản nâng cấp `risk/runtime_risk_engine.py`)
- **Mục đích:** Lớp khiên bảo vệ (Guardrails) của toàn hệ thống (Kill Switch, Max Drawdown halt, Exposure limit).
- **Workflow & Tương tác:**
  - Được Inject dưới dạng Dependency vào `core/orchestrator.py`.
  - Trước bất kỳ một Order nào hay định kỳ, Orchestrator sẽ gọi `evaluate_risk()`.
  - Nếu Risk Engine phát tín hiệu "HALT_TRADING", toàn bộ system sẽ ngưng đẩy lệnh.

### 4.2. RealTimeRiskEngine
- **Trạng thái:** CHƯA KẾT NỐI RÕ RÀNG TRONG CORE QUY TẮC (Standby)
- **File:** `risk/realtime.py`
- **Lý do chưa kết nối:** Có thể được sử dụng riêng biệt như một Dashboard Monitor chạy song song (Sub-process) theo dõi Websocket, tách biệt logic với Core Runtime Guardrails (`RuntimeRiskEngine`).

---

## 5. Nhóm Xử Lý Dữ Liệu (Data Integrity)

### 5.1. AdjustmentEngine
- **Trạng thái:** CHƯA KẾT NỐI MAIN FLOW (Standby)
- **File:** `data/quality.py`
- **Mục đích:** Xử lý và Re-scale Data khi có sự kiện chia tách cổ phiếu (Splits), cổ tức (Dividends) để Backtest không bị ngắt gãy.
- **Lý do chưa kết nối:** Thường được gọi bởi các background job ETL chạy ngoài giờ giao dịch (Crontab) trước khi lưu DB. Do đó không thấy xuất hiện trong flow chạy thực tế của System/Orchestrator lúc live.

---

## TỔNG QUAN WORKFLOW TƯƠNG TÁC CHÍNH CỦA HỆ THỐNG LIÊN KẾT:

1. **Giai đoạn Research (Nghiên Cứu)**:
   - File csv/db $\rightarrow$ **`FactorEngine`** (Tính năng) $\rightarrow$ **`AlphaEngine`** (Lọc Tín Hiệu) $\rightarrow$ **`VectorizedEngine`** (Đánh giá Backtest P&L).

2. **Giai đoạn Live Trading Loop (Vận Hành Thực Tế)**:
   - Data Stream $\rightarrow$ `EnsembleStrategy` (Với trọng số cấu hình từ **`MetaLearningEngine`**) $\rightarrow$ Tạo Signal.
   - Signal $\rightarrow$ **`TradingOrchestrator`** $\rightarrow$ Check qua **`RuntimeRiskEngine`** (Đảm bảo không vượt quá Drawdown).
   - Nếu Risk Pass $\rightarrow$ Pass sang `ExecutionLayer` (**`ExecutionEngine`** hoặc **`PaperTradingEngine`**).
   - `ExecutionLayer` trả về `FillEvent` (Đã khớp lệnh) $\rightarrow$ **`FeedbackEngine`** phân tích chất lượng lệnh gởi (Slippage, Loss) $\rightarrow$ Update ngược lại trạng thái vào **`MetaLearningEngine`**.
