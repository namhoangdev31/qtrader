# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: PHÒNG NGHIÊN CỨU & QUẢN TRỊ DỮ LIỆU (RESEARCH)

**Vị trí**: `qtrader/research/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.25`  
**Mục tiêu**: Giải phẫu môi trường Jupyter Notebook Sandbox (Lab) dành cho các Nhà phân tích định lượng (Quant Analysts). Đây là khối mã nguồn tương tác trực tiếp với con người (Human-in-the-loop) thay vì tự trị 100% như các khối Bot khác. Định dạng tài liệu tiếp tục chuẩn **Giải phẫu Sâu Từng File (File-by-File)**.

---

## 1. FILE: `session.py` (Trung tâm Chỉ huy Notebook - `AnalystSession`)

Sở hữu lớp đa năng `AnalystSession`. Lớp này gom tất cả những công cụ khó dùng nhất của hệ thống lõi lại thành các hàm gọi lệnh (API) mượt mà cho 3 Role chính: **Analyst** (EDA Dữ liệu), **Researcher** (Tạo Đặc trưng ML), **Trader** (Kiểm toán mạng sống Bot).

### 1.1 Khối Chống đứt gãy Dữ liệu (4-Tier Data Fallback)

Hàm `load_from_datalake` được bảo vệ bằng thiết kế giật cấp 4 tầng. Nếu hệ thống ngã ở bước trước, nó tự bật dù lấy dữ liệu ở rặng tiếp theo thay vì báo lỗi đứng máy:

1. **Tầng Ưu tiên**: Đọc từ `DuckDB`.
2. **Tầng Khẩn Cấp Cục Bộ**: Truy đòi file trong `UniversalDataLake` (JSON/Parquet).
3. **Tầng Viết Lại Từ Mạng Live**: Xin nạp thẳng chuỗi REST API trực tiếp từ `CoinbaseMarketDataClient` và save đè ngược lại DataLake để lần sau đọc nhanh hơn.
4. **Tầng Ảo Ảnh Bất tử**: Sinh ra cây Fake OHLCV (từ `generate_synthetic_data` - Mẫu Dữ liệu ngẫu nhiên) để Research Code bằng mọi giá vẫn phải chạy.

### 1.2 Khối Thống kê Định lượng & Chỉ báo (Quantitative Stats & Rolling)

* **Hàm `rich_describe`**: Trả về dữ liệu lớn hơn nhiều lệnh `describe()` của Pandas. Xuyên thủng Polars để quét rác ngoại lại với thuật toán IQR (Outlier), tính độ xiên `skew` và độ nhọn `kurtosis` (Sóng có rủi ro đuôi Fat-tail hay không). Phục vụ cực kỳ tốt cho chuẩn bị Data MLOps.
* **Hàm `add_rolling_features`**: Inject 2 chỉ báo Volatility động học `vol_w` và Xung lượng `rsi_14` bằng `clip` gốc của Polars, loại trừ độ trễ tính toán.

### 1.3 Khối Đo đạc Hiệu suất Định chế (Extended Metrics)

Hệ thống cho phép cắm Object `BaseEngine` lôi Data từ quá khứ và đo lường thông qua `compute_extended_metrics`:

* Tính chu kỳ trượt lỗ **Sortino Ratio** (Lọc loại bỏ dao động văng Lãi để tập trung đo Rủi Ro).
* Hệ số sức bền hình phạt **Calmar Ratio** (Lãi ròng chia Drawdown tối đa).

### 1.4 Khối Thử nghiệm Chiến đấu Mạng Sống (Trader Connectivity)

* Cung cấp tính năng mô phỏng `run_paper_simulation` và đo L2 Orderbook (`get_live_orderbook`) không cần qua OMS.

* Cấp quyền gọi lệnh siêu bảo mật `ping_live_api` bằng HTTP Request tới cổng 8000 của Bot chạy ngầm. Giúp rút báo cáo Real-time (PnL, Regime, Active Model).

---

## 2. FILE: `report.py` (Cỗ máy In ấn Điện tử - `ReportBuilder`)

Không phụ thuộc vào Jupyter Notebook, QTrader trang bị thẳng một máy in Báo cáo Tĩnh nội bộ dựa trên Python Thuần.

### 2.1 CSS Nhúng Cơ sở Trái tuyến

Class tự động kẹp bộ thẻ `<style>` (Dark theme tinh xảo `#0f1117`, `#a5f3fc`) vào mã để loại trừ phụ thuộc Bootstrap hoặc CDN Mạng. Báo cáo HTML này tải và xem được ở máy bay hoặc hầm chứa Server không có Internet.

### 2.2 Trình Dịch Cấu Trúc Động (Polars & B64 Base Render)

1. **Dịch Biểu Đồ Matplotlib (`add_figure`)**: Bản đồ/Chart không lưu thành ngàn file PNG rác rưởi. ReportBuilder gọi hàm save `png` nhét vào Memory, băm ra chuỗi mã base64 và dán cứng bằng chuỗi `<img src="data:image/png;base64,{b64}">`. Toàn bộ dữ liệu nằm trong 1 File HTML duy nhất.
2. **Dịch Bảng Giá Trị (`add_table`)**: Tự động iter qua bộ cột Polars sinh ra mã tag HTML Table. Biến hình bất cứ Dictionary rác nào thành dạng 2 Cột Metric-Value tiêu chuẩn.
3. Chức năng `build_html()` sinh chữ ký kiểm toán Audit Timestamp dưới chân trang.

---

**KẾT LUẬN AUDIT**:
Module `qtrader/research` vượt xa danh mục "thư mục Script" lộn xộn. Nó được quy hoạch quy củ như một bàn điều khiển Data Science tiêu chuẩn công nghiệp (Analytics Sandbox). Thiết kế của nó triệt tiêu các lỗi ngớ ngẩn (như rớt mạng Data) bằng tư duy 4 tầng fallback, và mã hóa việc xuất thông tin thành báo cáo 1 tệp tĩnh cực kỳ tiện lợi cho Quant Report.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Research File-by-File Deep Audit - Implemented)`
