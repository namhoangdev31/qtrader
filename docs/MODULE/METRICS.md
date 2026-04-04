# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: METRICS & ANALYTICS

**Vị trí**: `qtrader/metrics/` & `qtrader/analytics/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.18`  
**Mục tiêu**: Thiết lập hệ thống "Mắt thần" (Eyes of the System) – từ đo lường hiệu suất (Performance), kế toán tài sản (NAV), phân tích chi tiết chi phí (TCA) đến giám sát sự suy thoái chiến lược (Alpha Decay).

---

## 1. HỆ THỐNG TELEMETRY & PIPELINE (METRICS CORE)

### 1.1 `telemetry_pipeline.py`: Snapshot Worker
Hệ thống vận hành một worker chạy ngầm để thu thập trạng thái định lượng của toàn bộ engine:
- **Chu kỳ**: Snapshot mỗi 5 giây (`interval_seconds=5.0`).
- **Lưu trữ**: Ghi vết nguyên tử (Atomic write) vào `metrics_registry.json` để làm cơ sở cho việc hậu kiểm (Audit trail).
- **Snapshot Logic**: Chụp toàn bộ trạng thái của `qtrader.core.metrics` bao gồm độ trễ API, tần suất lệnh và trạng thái tài nguyên.

---

## 2. BỘ MÁY PHÂN TÍCH HIỆU SUẤT (PERFORMANCE ENGINE)

### 2.1 `performance.py`: Vectorized Analytics
QTrader sử dụng Polars để tính toán các chỉ số hiệu suất với tốc độ định chế:

| Chỉ số | Logic Xử lý (Institutional Standard) |
| :--- | :--- |
| **CAGR** | Tính toán tỉ lệ tăng trưởng kép hàng năm |
| **Annualized Vol** | `returns.std() * sqrt(252)` |
| **Sharpe Ratio** | `(Return - RiskFree) / Vol`. Điểm số > 2.0 được coi là đạt chuẩn định chế. |
| **Max Drawdown** | Tính toán sụt giảm tối đa từ đỉnh tài sản (Peak-to-Trough) — Chốt chặn rủi ro chính. |

- **`calculate_metrics()`**: Hàm lõi nhận vào chuỗi Equity Curve và trả về từ điển hiệu suất đầy đủ.

---

## 3. KẾ TOÁN QUỸ & NAV (FUND ACCOUNTING)

### 3.1 `accounting.py`: Mark-to-Market (MtM) Valuation
Lớp `FundAccountingEngine` đảm bảo tính minh bạch tài chính tuyệt đối:
- **NAV (Net Asset Value)**: $NAV = Assets - Liabilities$.
- **Real-time MtM**: Định giá lại toàn bộ danh mục ngay lập tức dựa trên giá thị trường (`market_prices`).
- **NAV Certification**: Hệ thống tự động theo dõi `peak_nav_historical` để kiểm soát ngưỡng Watermark (Phục vụ tính toán Performance Fee trong tương lai).

---

## 4. PHÂN TÍCH CHI PHÍ GIAO DỊCH (TCA ENGINE)

### 4.1 `tca_engine.py`: Execution Quality Measurement
Phân tích chi tiết từng micro-cent bị mất trong quá trình thực thi (Standash §8.1):

- **Implementation Shortfall (IS)**: 
  $$IS = (fill\_price - decision\_price) \times side$$
- **Slippage Decomposition (Bóc tách trượt giá)**:
    - **Timing Slippage**: Sai lệch giữa lúc ra quyết định và lúc lệnh đến thị trường.
    - **Market Impact**: Tác động của chính lệnh đó lên giá thị trường.
    - **Fee Slippage**: Chi phí phí sàn (Maker/Taker).
- **VWAP Deviation**: Độ lệch so với giá trung bình trọng số khối lượng (Benchmark định chế).

---

## 5. GÁN NHÃN LỢI NHUẬN (PNL ATTRIBUTION)

### 5.1 `pnl_attribution.py`: Nguồn gốc Lợi nhuận (Alpha vs. Beta)
Bóc tách từng đô la lợi nhuận/thua lỗ để xác định lỗi thuộc về tín hiệu (Alpha) hay thực thi (Execution):

- **Alpha PnL**: $(decision\_price - fair\_value) \times quantity$ (Hiệu quả của Signal).
- **Execution PnL**: $(decision\_price - fill\_price) \times quantity$ (Hiệu quả của SOR/Broker).
- **Fee PnL**: Tổng chi phí phí giao dịch.

---

## 6. GIÁM SÁT ĐỘ LỆCH & SUY THOÁI CHIẾN LƯỢC (DRIFT & DECAY)

### 6.1 `drift.py`: Statistical Health Monitoring
Sử dụng các kiểm định thống kê tiên tiến để phát hiện khi nào Alpha bắt đầu lỗi thời:

- **Population Stability Index (PSI)**:
    - **PSI < 0.1**: Không có thay đổi (Safe).
    - **0.1 < PSI < 0.25**: Thay đổi nhẹ (Warning).
    - **PSI > 0.25**: Thay đổi nghiêm trọng (Critical Drift - Alpha Decay).
- **Kolmogorov-Smirnov (KS) Test**: Kiểm định sự khác biệt về phân phối giữa dữ liệu Train (Quá khứ) và Live (Hiện tại). Nếu `p_value < 0.05`, hệ thống sẽ kích hoạt cảnh báo Drift.

---

**KẾT LUẬN AUDIT**: Module Metrics & Analytics của QTrader đạt chuẩn **Institutional Metrology §8.4**. Hệ thống cung cấp độ sâu phân tích vượt trội so với các bot trading thông thường, đặc biệt là khả năng bóc tách PnL Attribution và giám sát Drift thống kê – yếu tố then chốt để duy trì lợi thế cạnh tranh dài hạn.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Metrics Deep Audit - Finalized)`
