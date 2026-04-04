# PHÂN TÍCH CHI TIẾT MODULE: BACKTEST (STRATEGIC SIMULATION & PERFORMANCE AUDITING)

**Vị trí**: `qtrader/backtest/`
**Mục tiêu**: Cung cấp môi trường thử nghiệm chiến lược với độ trung thực cao (high-fidelity), loại bỏ hoàn toàn các sai lệch thống kê (biases) và mô phỏng chính xác các chi phí ma sát của thị trường.

---

## 1. ĐỘNG CƠ VECTO HÓA CẤP ĐỘ QUỸ (INSTITUTIONAL VECTORIZED ENGINE)

### 1.1 Lớp `VectorizedEngine` (`engine_vectorized.py`)

Khác với các công cụ backtest thông thường chạy theo vòng lặp, `VectorizedEngine` thực hiện toàn bộ phép tính trên mảng dữ liệu (Vectorized) bằng Polars, giúp tốc độ xử lý nhanh hơn gấp 100-1000 lần.

- **Giải thuật Lõi (`backtest()` Method)**:
  - **Lookahead Prevention**: Tín hiệu (`signal`) tại thời điểm `t` được dịch chuyển (`shift(1)`) để trở thành tín hiệu thực thi tại thời điểm `t+1`. Điều này đảm bảo bạn không bao giờ mua được ở mức giá "đã biết trước".
  - **Mô hình Market Impact (Tác động thị trường)**:
    - Công thức chuẩn: `Impact_Bps = σ_daily * sqrt(OrderSize / DailyVolume)`.
    - Hỗ trợ các mô hình: `square_root`, `linear`, `almgren_chriss`. Giúp mô phỏng hiện tượng giá chạy khỏi lệnh khi giao dịch khối lượng lớn.
  - **Turnover Awareness**: Chi phí giao dịch (`_cost`) chỉ được tính trên phần thay đổi vị thế (`delta_position`), giúp phản ánh chính xác phí hoa hồng và thuế.
  - **Borrowing Costs (Phí vay)**: Tự động trừ phí margin hàng ngày cho các vị thế Bán khống (Short) dựa trên `borrowing_cost_annual_bps`.

- **Mạch Backtest đa tài sản (`cross_sectional_backtest()`)**:
  - Thực hiện **Ranking** (xếp hạng) toàn bộ danh mục theo Signal.
  - Phân bổ tỷ trọng (Weighting) cho Top-N long và Bottom-N short.
  - Tự động tái cân bằng (Rebalance) theo chu kỳ: Daily, Weekly, Monthly.

---

## 2. HỆ THỐNG PHÂN TÍCH HIỆU QUẢ CHUYÊN SÂU (`tearsheet.py`)

### 2.1 Lớp `TearsheetGenerator`

Biến kết quả thô từ Engine thành một bản báo cáo phân tích rủi ro toàn diện.

- **Các chỉ số rủi ro nâng cao (Advanced Metrics)**:
  - **Omega Ratio**: Đo lường xác suất đạt được mục tiêu lợi nhuận so với rủi ro thua lỗ (tốt hơn Sharpe khi phân phối không chuẩn).
  - **Calmar Ratio**: Tỷ lệ lợi nhuận năm trên mức sụt giảm tối đa (`Ann_Return / Max_Drawdown`).
  - **Win-Rate & Profit Factor**: Suy luận logic dựa trên sự thay đổi trạng thái tín hiệu (`_exec_signal`) để thống kê số lệnh thắng/thua thực tế.
  - **Hệ số Bất đối xứng (Skewness & Kurtosis)**: Đánh giá xác suất xảy ra các sự kiện "Thiên nga đen" (Fat Tails).

- **Trực quan hóa (Interactive Charts)**:
  - **Equity Curve**: Biểu đồ tăng trưởng tài sản.
  - **Underwater Drawdown**: Biểu đồ sụt giảm tài sản (Crimson color) để theo dõi thời gian phục hồi.
  - **Rolling Sharpe**: Theo dõi sự thay đổi của hiệu quả điều chỉnh rủi ro qua từng cửa sổ thời gian.

---

## 3. QUY TRÌNH KIỂM KIỂU (SIMULATION WORKFLOW)

1. **Dữ liệu đầu vào**: DataFrame Polars đã được chuẩn hóa (OHLCV).
2. **Signal Generation**: Các Alpha (Momentum, Mean-Rev) tạo ra tín hiệu [-1, 1].
3. **Engine Execution**: Tính toán `Net_Return` sau khi trừ Slippage, Commission và Borrowing Cost.
4. **Tearsheet Export**: Xuất ra tệp HTML tương tác và tệp JSON Sidecar.
5. **Baseline Comparison**: Tệp JSON được dùng để so sánh với hiệu suất Live thực tế (Detect Strategy Drift).

---

## 4. MA TRẬN KẾT NỐI (CONNECTIVITY MATRIX)

| Module Gốc | Module Đích | Dữ liệu truyền tải |
| :--- | :--- | :--- |
| **Alpha** | Backtest | Tín hiệu giao dịch thô (`_exec_signal`) |
| **Analytics** | Tearsheet | Thư viện chỉ số Sharpe, MDD, Volatility |
| **Research** | Backtest | Cấu hình tham số kiểm thử (Hyperparameters) |
| **Execution** | Backtest | Mô hình Slippage thực tế từ lịch sử Live |

---

## 5. NHỮNG LỖ HỔNG CẦN LƯU Ý (SIMULATION GAPS)

Mặc dù rất mạnh mẽ, Backtest Module vẫn đối mặt với các giới hạn:

- **Zero-Latency Assumption**: Backtest coi như lệnh khớp ngay tại giá Open/Close tiếp theo, chưa tính đến độ trễ mạng thực tế (Network Latency) trong HFT.
- **Orderbook Depth**: Mô hình Market Impact chỉ là ước tính toán học, không thay thế được việc mô phỏng khớp lệnh trực tiếp trên sổ lệnh (L2 Orderbook Simulation).
- **Survival Bias**: Hệ thống yêu cầu dữ liệu sạch, nếu dữ liệu thiếu các mã đã bị hủy niêm yết (delisted), kết quả sẽ bị sai lệch.

---

**KÝ XÁC NHẬN PHÂN TÍCH**: `Antigravity AI Agent (Deep Simulation Audit Ver 4.7)`
