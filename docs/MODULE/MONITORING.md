# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: MONITORING & ALERTING

**Vị trí**: `qtrader/monitoring/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.22`  
**Mục tiêu**: Phân tích cơ chế MRO (Monitoring, Reporting, Observability). Minh họa cách hệ thống xuất metrics tự động bằng HTTP Server tích hợp và cơ chế bắn thông báo (Alerting) đa nền tảng không đồng bộ (non-blocking).

---

## 1. KHỐI PROMETHEUS METRICS KHÔNG PHỤ THUỘC (STANDALONE EXPORTER)

QTrader không cài cắm bộ cài lớn (như `prometheus_client`) mà **tự xây dựng một Registry In-memory** sinh ra dữ liệu chuỗi văn bản (plaintext metrics) chuẩn xác cho Grafana.

**Vị trí**: `prometheus_metrics.py`

- Tích hợp một máy chủ HTTP hạng nhẹ (sử dụng `aiohttp` web server) chạy ẩn trên cổng `9090` qua đường dẫn định tuyến `/metrics` và `/health`.
- Chứa 3 loại khối dữ liệu lõi:
  - **Counters**: Biến đếm liên tục tích lũy (ví dụ: Số lệnh đã mở).
  - **Gauges**: Đồng hồ đo trạng thái hiện thời, có thể tăng giảm (ví dụ: Unrealized PnL, Khối lượng Inventory).
  - **Histograms**: Phục vụ việc đánh giá phân phối phần trăm (nhanh chóng tính ra `_count`, `_sum`, `_avg`). Dùng nhiều nhất để đo Phân bố Độ trễ (Latency Heatmap).

### Danh mục Lõi (Core Metrics Schema)

Định dạng này giúp đội DevOps dễ dàng config thẳng vào Grafana:

| Metric Name (Prometheus Key) | Dạng | Mô tả |
| :--- | :--- | :--- |
| `qtrader_orders_submitted_total` | Counter | Tổng lệnh đã nạp xuông sàn. |
| `qtrader_fills_total` | Counter | Tổng lệnh Order đã khớp hoàn toàn. |
| `qtrader_fill_latency_ms` | Histogram | Phân bố độ trễ từ lúc đặt lệnh đến lúc có kết quả Fill. |
| `qtrader_pnl_realized` / `unrealized` | Gauge | Biến thiên lợi nhuận ròng PnL. |
| `qtrader_var` / `qtrader_drawdown` | Gauge | Giá trị Value-at-Risk và Sụt giảm tài sản (Risk Management). |
| `qtrader_kill_switch_active` | Gauge | Flag nhị phân (1.0 = Cắt cầu dao, 0.0 = Bình thường). |
| `qtrader_exchange_connected` | Gauge | Theo dõi nhịp đập kết nối Websocket tới sàn (Health check). |

*(Gợi ý Grafana: Có thể kết hợp `qtrader_fill_latency_ms_avg` và `qtrader_exchange_latency_ms_avg` trên cùng một biểu đồ để phát hiện cổ chai (bottleneck) mạng).*

---

## 2. KHỐI CẢNH BÁO ĐA KÊNH TRUYỀN THÔNG (ALERT ENGINE)

Bắn tín hiệu rủi ro ra thế giới thực mà không làm Block bất kỳ tiểu trình Trading thuật toán nào.

**Vị trí**: `alert_engine.py` (Kế thừa Tiêu chuẩn Standash §5.4)

### Cấp độ Cảnh báo (Severity)

Sử dụng mã màu (Color Mapping) cho Slack webhook hiển thị trực quan:

- `INFO`: Thông báo chuyển trạng thái thông thường (#36a64f - Xanh).
- `WARNING`: Cảnh báo rủi ro ban đầu (Ví dụ: Margin sử dụng > 50%) (#ffaa00 - Cam).
- `CRITICAL`: Các tình huống ngắt cầu dao (Kill-switch) hoặc Disconect API (#ff0000 - Đỏ rực).

### Các Kênh Mở Rộng

Sử dụng `asyncio.gather` để Broadcast lệnh song song với giới hạn Time-out là 10 giây (đảm bảo không bị treo rác Thread):

1. **Slack**: Sử dụng ClientSession của `aiohttp` để xả JSON Payload bào Slack Webhook.
2. **SMTP/Email**: Gửi thư rác cứu trợ thông qua giao thức TLS.
3. **PagerDuty**: Post Alert trực tiếp lên API Sự kiện (Event API) của PagerDuty để đánh thức kỹ sư trực ca ban đêm. Nếu trả về `202`, lệnh Cứu hộ thành công.

---

## 3. KHỐI TỔNG HỢP WAR ROOM (WARROOM METRICS AGGREGATOR)

Tích hợp một Aggregator trong bộ nhớ sử dụng riêng cho **Các bảng điều khiển trực tiếp (War Room Dashboards)**.

**Vị trí**: `metrics.py` (`MetricsAggregator`)

- Hoạt động giống như lớp "biến cục bộ cấp cao", kẹp khối lượng (Total Volume) và Nominal (`price * qty`) mỗi khi `on_fill()` được gọi.
- Gom dữ liệu của các mã giao dịch (`symbol_fills`, `symbol_volume`) thành tệp tin JSON siêu nhẹ gọi qua `get_summary()`.
- Thời gian cập nhật tự động gắn nhãn (Timestamp UTC).

---

**KẾT LUẬN AUDIT**: Module Monitoring được thiết kế cực kỳ thông minh khi không chọn lối mòn nhồi nhét thư viện (dependency-bloat). Việc tự Build Prometheus HTTP Server qua `aiohttp` kết hợp Async Alert Engine chứng tỏ kiến trúc sư am hiểu nguyên lý Low-Latency (Độ trễ thấp). Module đạt chuẩn cấu trúc **Standash Observability §5.4**.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional MRO Deep Audit - Finalized)`
