# PHÂN TÍCH CHI TIẾT MODULE: ANALYTICS (FISCAL GOVERNANCE & FORENSIC AUDITING)

**Vị trí**: `qtrader/analytics/`
**Mục tiêu**: Đảm bảo tính xác thực tài chính tuyệt đối, đo lường hiệu quả thực thi và phát hiện sớm các rủi ro hệ thống thông qua toán học thống kê.

---

## 1. HỆ THỐNG KẾ TOÁN QUỸ (`accounting.py`)

Đây là lớp "Kế toán trưởng" của toàn bộ hệ thống, chịu trách nhiệm định giá tài sản theo thời gian thực.

### 1.1 Lớp `FundAccountingEngine`
Chứa logic tính toán Giá trị tài sản ròng (NAV) và Lợi nhuận chưa thực hiện (Unrealized PnL).

- **Phương thức `update_financial_state()`**:
  - **Đầu vào**: Danh sách vị thế (`positions`), bảng giá thị trường (`market_prices`), số dư tiền mặt (`cash_balance`).
  - **Toán học MtM (Mark-to-Market)**: 
    - `Unrealized PnL = Σ (CurrentPrice_i - EntryPrice_i) * Quantity_i`
    - `Total Assets = Cash + Σ (EntryPrice_i * |Quantity_i|) + Unrealized PnL`
    - `NAV = Total Assets - Liabilities`
  - **Chứng chỉ định giá (Certification Artifact)**: Trả về một dictionary chứa toàn bộ trạng thái tài chính, bao gồm cả "Độ trễ định giá" (valuation latency) để đảm bảo tính kịp thời.

### 1.2 `drift.py`: Phát hiện lỗi thời Alpha
Sử dụng AI và thống kê để biết khi nào mô hình không còn "khớp" với thị trường.

- **`DriftMonitor.calculate_psi()`**: Tính chỉ số ổn định dân số (**Population Stability Index**).
  - Giúp phát hiện sự thay đổi trong hành vi của các đặc trưng (features) đầu vào.
  - Ngưỡng cảnh báo: PSI > 0.2 (Warning), PSI > 0.3 (Critical).
- **`DriftMonitor.detect_drift()`**: 
  - Sử dụng kiểm định **Kolmogorov-Smirnov (KS)** để so sánh phân phối giữa dữ liệu Train và dữ liệu Live.
  - Nếu `p-value < 0.05`, hệ thống sẽ đánh dấu là có sự sai lệch phân phối (Data Drift).

---

## 2. PHÂN TÍCH CHI PHÍ GIAO DỊCH (TCA - `tca_engine.py`)

Module này mổ xẻ từng lệnh giao dịch để tìm ra nơi "tiền bị rơi rớt" do lỗi thực thi hoặc do thị trường.

### 2.1 Lớp `TCAEngine`
Xử lý dữ liệu lệnh theo lô (batch) hoặc từng lệnh lẻ (real-time).

- **Phương thức `analyze_batch()` (Vectorized Polars)**:
  - **Implementation Shortfall (IS)**: Đo lường tổng chi phí thực hiện.
    - `IS = (FillPrice - DecisionPrice) * Side * Quantity`
  - **Phân rã trượt giá (Slippage Decomposition)**:
    - **Timing Slippage**: `ArrivalPrice - DecisionPrice`. Lỗi do hệ thống gửi lệnh chậm.
    - **Impact Slippage**: `FillPrice - ArrivalPrice`. Lỗi do kích thước lệnh quá lớn làm biến động giá.
    - **Fee Slippage**: Phí hoa hồng sàn giao dịch quy đổi ra mỗi cổ phiếu/token.
  - **VWAP Deviation**: Độ lệch so với giá trung bình trọng số khối lượng (`FillPrice - BenchmarkPrice`).

---

## 3. CHỈ SỐ HIỆU SUẤT VÀ ĐỘ TIN CẬY (`performance.py`)

Cung cấp cái nhìn định lượng về hiệu quả của chiến lược qua thời gian.

### 3.1 Lớp `PerformanceAnalytics`
Tận dụng Polars để tính toán trên các chuỗi thời gian (Timeseries) khổng lồ mà không gây trễ.

- **Các chỉ số cốt lõi**:
  - **Sharpe Ratio**: `(Annualized Return - Risk Free Rate) / Annualized Volatility`.
  - **Sortino Ratio**: Tương tự Sharpe nhưng chỉ tính độ biến động của các nhịp sụt giảm (Downside Volatility).
  - **Max Drawdown (MDD)**: Tính từ đỉnh cao nhất (`cum_max`) đến đáy thấp nhất. QTrader báo cáo MDD dưới dạng % dương (Institutional Standard).
- **Logic xử lý**: Tự động hóa việc làm sạch dữ liệu (`drop_nulls`) và chuẩn hóa kỳ hạn (annualization) 252 ngày giao dịch.

---

## 4. GIÁM SÁT REAL-TIME (`telemetry.py`)

Cung cấp dữ liệu cho các Dashboard giám sát (Grafana/Prometheus).
- Theo dõi **Valuation Cycle Count**: Đảm bảo Engine kế toán đang chạy đều đặn.
- Theo dõi **Peak NAV Historical**: Ghi nhận mức đỉnh tài sản để tính toán các ngưỡng cắt lỗ vĩ mô.

---

## 5. MA TRẬN KẾT NỐI (CONNECTIVITY MATRIX)

| Module Gốc | Module Đích | Dữ liệu truyền tải |
| :--- | :--- | :--- |
| **OMS** | Accounting | `PositionState`, `EntryPrice`, `CashBalance` |
| **Execution** | TCA | `DecisionPrice`, `FillPrice`, `FeeRate` |
| **Alpha / ML** | Drift | `FeatureVectors`, `SignalPredictions` |
| **Backtest** | Performance | `EquityCurve`, `NetReturns` |
| **Global Risk** | Accounting | `NAV Snapshot` (để kích hoạt Kill Switch nếu NAV < Margin Call) |

---

## 6. TIÊU CHUẨN ĐỘ CHÍNH XÁC (INSTITUTIONAL PRECISION)

Mặc dù `ANALYTICS` là lớp giám sát, nó phải đối mặt với rủi ro **NAV Drift**:
- **Nguyên nhân**: Sử dụng kiểu dữ liệu `float` dẫn đến sai số làm tròn sau hàng triệu phép tính.
- **Giải pháp QTrader**: Đang trong lộ trình chuyển đổi tất cả phép tính MtM sang `Decimal` (Sử dụng `decimal_adapter.py`). Mọi báo cáo cuối cùng đều được `round()` về 4 hoặc 6 chữ số thập phân để đảm bảo tính nhất quán giữa nội bộ và báo cáo sàn.

---

**KÝ XÁC NHẬN PHÂN TÍCH**: `Antigravity AI Agent (Comprehensive Analysis Ver 4.6)`
