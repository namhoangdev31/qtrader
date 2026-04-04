# PHÂN TÍCH CHI TIẾT MODULE: COMPLIANCE (MARKET INTEGRITY & SURVEILLANCE)

**Vị trí**: `qtrader/compliance/`
**Mục tiêu**: Đảm bảo mọi hoạt động giao dịch tuân thủ các quy định pháp lý (MiFID II, Reg NMS), ngăn chặn thao túng thị trường và cung cấp khả năng hậu kiểm (Forensic Audit) hoàn hảo.

---

## 1. HỆ THỐNG GIÁM SÁT THỊ TRƯỜNG (MARKET SURVEILLANCE)

### 1.1 `surveillance_engine.py`: Động cơ phát hiện vi phạm
Lớp giám sát cấp cao, phân tích chuỗi sự kiện để tìm ra các dấu hiệu trục lợi.
- **Wash Trading (Tự khớp)**: Phát hiện các lệnh Mua/Bán đối ứng cho cùng một User/Symbol trong một cửa sổ thời gian cực ngắn (mặc định 100ms).
- **Spoofing (Đặt lệnh ảo)**: Phát hiện việc đặt các lệnh lớn rồi hủy ngay lập tức nhằm đánh lừa thị trường về thanh khoản.
- **Quote Stuffing (Nhồi lệnh)**: Phát hiện tỷ lệ Hủy/Đặt (>90%) và tốc độ gửi tin nhắn (>100 msg/s) bất thường nhằm gây trễ cho các thành phần khác của thị trường.

### 1.2 `spoof_detector.py`: Máy dò thao túng chuyên sâu
Một công cụ trạng thái (stateful) giúp tích lũy dữ liệu lịch sử để xác định "ý đồ" thao túng.
- **Chỉ số quyết định**: 
  - **Cancel Rate (CR) > 90%**: Tỷ lệ hủy lệnh áp đảo.
  - **Fill Rate (FR) < 5%**: Tỷ lệ khớp lệnh cực thấp.
  - **Short-lived orders**: Các lệnh có tuổi thọ < 200ms chiếm đa số.
- **Quorum Check**: Chỉ kích hoạt cảnh báo khi có đủ mẫu số liệu (mặc định 10 lệnh) để tránh báo động giả (False Positives).

---

## 2. TRUY XUẤT NGUỒN GỐC GIAO DỊCH (TRADE LINEAGE)

### 2.1 `lineage_tracker.py`: Sợi chỉ đỏ xuyên suốt vòng đời lệnh
Đảm bảo tính minh bạch từ lúc sinh tín hiệu đến khi kết thúc vị thế.
- **Chuỗi Lineage Record**: `Signal_ID -> Decision_ID -> Order_ID -> Fill_ID -> Position_ID`.
- **Bi-directional Trace (Truy vết ngược xuôi)**: Cho phép trả lời câu hỏi: "Lệnh khớp (Fill) này được sinh ra từ tín hiệu Alpha nào?" hoặc "Tín hiệu Alpha này cuối cùng đã dẫn đến vị thế nào?".
- **Audit Fidelity**: Tự động đánh giá tính "Hoàn tất" (Completeness) của một chuỗi giao dịch để đảm bảo dữ liệu không bị thất lạc trong quá trình xử lý.

---

## 3. KIỂM SOÁT VỊ THẾ BẮT BUỘC (POSITION LIMITING)

### 3.1 `position_limiter.py`: Cổng chặn giao dịch (Pre-trade Gate)
Cơ chế kiểm soát "cứng" (Hard Gate) không thể bị bỏ qua trước khi gửi lệnh lên sàn.
- **Symbol Concentration**: Giới hạn sự tập trung vốn vào một tài sản nhất định để tránh rủi ro hệ thống.
- **Aggregate Exposure**: Giới hạn tổng mức tiếp xúc (Exposure) của toàn bộ tài khoản.
- **Offsetting Exception**: Tự động cho phép các lệnh làm giảm quy mô vị thế (Risk-reducing orders) ngay cả khi đã vượt hạn mức, giúp hệ thống luôn có thể thoát hàng (Unwind).

---

## 4. CÔNG BỐ RỦI RO & BÁO CÁO (RISK DISCLOSURE)

### 4.1 `risk_disclosure.py`: Báo cáo minh bạch auditable
Tạo ra các bản báo cáo rủi ro không thể chối cãi.
- **Metric Vectorization**: Tính toán VaR (Value at Risk) 99%, Max Drawdown và Volatility hàng năm.
- **Data Fingerprinting**: Sử dụng mã băm **SHA-256** cho dữ liệu đầu vào. Điều này giúp kiểm toán viên xác minh rằng báo cáo không bị chỉnh sửa sau khi xuất bản.
- **Reproducibility**: Đảm bảo kết quả báo cáo luôn giống nhau nếu dữ liệu đầu vào không đổi.

---

## 5. MA TRẬN KẾT NỐI (CONNECTIVITY MATRIX)

| Đến Module | Cách kết nối | Mục đích |
| :--- | :--- | :--- |
| **`qtrader/execution/`** | Cổng can thiệp (Interceptor) | `PositionLimiter` chặn lệnh ngay trước khi qua Adapter. |
| **`qtrader/oms/`** | Đồng bộ trạng thái | `LineageTracker` lấy ID từ OMS để gắn kết chuỗi. |
| **`qtrader/alpha/`** | Điểm bắt nguồn | Lấy `Signal_ID` làm điểm neo đầu tiên cho Lineage. |
| **`Exchange APIs`** | Giám sát luồng L2 | `SurveillanceEngine` phân tích các sự kiện gửi về từ sàn. |

---

**KÝ XÁC NHẬN PHÂN TÍCH**: `Antigravity AI Agent (Market Integrity Audit Ver 4.9)`
