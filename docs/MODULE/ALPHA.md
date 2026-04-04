# PHÂN TÍCH CHI TIẾT MODULE: ALPHA (QUANTITATIVE SIGNAL GENERATION)

**Vị trí**: `qtrader/alpha/`
**Mục tiêu**: Tạo ra lợi thế cạnh tranh (Edge) thông qua việc trích xuất các tín hiệu dự báo từ dữ liệu thị trường bằng toán học định lượng và trí tuệ nhân tạo.

---

## 1. CƠ SỞ HẠ TẦNG TÍN HIỆU (ABSTRACTION & REGISTRY)

### 1.1 Lớp Cơ sở (`base.py`)

Thiết lập các tiêu chuẩn công nghiệp cho việc phát triển Alpha.

- **Protocol `Alpha`**: Ràng buộc mọi Alpha phải có hàm `compute(df: pl.DataFrame) -> pl.Series`.
- **Hàm `_zscore(series, window)`**: Một công cụ thiết yếu để chuyển đổi các giá trị thô thành "điểm chuẩn hóa". Nó giúp mọi tín hiệu (giá, khối lượng, RSI) có cùng một thang đo trung bình 0 và độ lệch chuẩn 1, cho phép chúng được cộng dồn trực tiếp.

### 1.2 Động cơ Điều phối (`registry.py`)

- **`AlphaRegistry`**: Quản lý vòng đời của Alpha. Hỗ trợ việc khởi tạo Alpha bằng tên từ cấu hình YAML/JSON.
- **`AlphaEngine.compute_all()`**:
  - Chạy song song danh sách Alpha được chỉ định.
  - **Cơ chế Trọng số (IC-Weighted Correlation)**: Tín hiệu cuối cùng (`composite_alpha`) được tính bằng:
    - `Weights_i = max(IC_i, 0) / Σ max(IC_j, 0)`
    - Điều này đảm bảo chỉ những Alpha có năng lực dự báo dương mới được tham gia vào quyết định giao dịch.

---

## 2. GIẢI THUẬT ALPHA CHI TIẾT (ALGORITHMIC BREAKDOWN)

### 2.1 Alpha Kỹ thuật phổ thông (`technical.py`)

- **`MomentumAlpha`**:
  - Công thức: `Signal = (LogReturn / RollingStd)`.
  - Đặc điểm: Tìm kiếm các tài sản đang có xu hướng mạnh nhưng rủi ro (biến động) thấp.
- **`MeanReversionAlpha`**:
  - Logic: Nghịch đảo của Z-score giá so với SMA. `Signal = -(Close - Mean) / Std`.
- **`TrendAlpha`**: Kết hợp SMA Crossover với bộ lọc **ATR (Average True Range)** để đo lường cường độ xu hướng.

### 2.2 Alpha Cấu trúc vi mô (`microstructure.py`) - Cấp độ HFT

- **`OrderImbalanceAlpha`**:
  - Công thức: `(BidSize - AskSize) / (BidSize + AskSize)`.
  - Ứng dụng: Dự báo hướng đi của giá trong vài giây/phút tới dựa trên áp lực mua/bán tại đầu sổ lệnh (L1).
- **`AmihudIlliquidityAlpha`**:
  - Công thức: `|Return| / (Price * Volume)`.
  - Tác dụng: Xác định các giai đoạn thanh khoản kém để chuẩn bị cho các nhịp đảo chiều mạnh.
- **`VPINAlpha` (Volume-Synchronized Probability of Informed Trading)**:
  - Logic: Ước tính xác suất có tin tức nội bộ dựa trên sự mất cân bằng khối lượng mua/bán tích lũy.

---

## 3. ENGINE ALPHA TĂNG CƯỜNG ML (`ml_alpha_engine.py`)

Đây là nơi hội tụ của "Atomic Trio" - tương lai của QTrader.

- **Quy trình Thực thi (The Pipeline)**:
    1. **Chronos-2**: Tiếp nhận chuỗi giá quá khứ, dự báo 24 nến tiếp theo (Forecasting).
    2. **TabPFN 2.5**: Phân loại rủi ro (Risk Class) dựa trên các đặc trưng phi tuyến tính của thị trường.
    3. **Phi-2**: Đọc kết quả từ 2 model trên, kết hợp với context thị trường để đưa ra quyết định (`BUY`, `SELL`, `HEDGE`, `HOLD`) kèm theo lời giải thích (Explainability).
- **Hybrid Fusion**: Tín hiệu cuối cùng là sự pha trộn (`ml_weight`=0.6, `traditional_weight`=0.4).

---

## 4. MA TRẬN KẾT NỐI (CONNECTIVITY MATRIX)

| Thành phần | Liên kết với | Phương thức trao đổi |
| :--- | :--- | :--- |
| **`AlphaEngine`** | `Data Lake` | Polars DataFrames (Vectorized) |
| **`MLAlphaEngine`** | `HuggingFace` | Tải Model Weights (Chronos, Phi-2) |
| **`DecayDetector`** | `Analytics` | Truy vấn Rolling IC để kiểm tra độ trễ |
| **`MetaSelector`** | `Strategy` | Cung cấp danh sách Alpha "Elite" cho Global Orchestrator |

---

## 5. CÁC ĐIỂM CẦN NÂNG CẤP (STRATEGIC GAPS)

Hệ thống Alpha hiện tại vẫn còn một số điểm cần giải quyết để đạt mức Institutional hoàn hảo:

1. **Naming Inconsistency**: Sự nhầm lẫn giữa `AlphaBase` và `BaseAlpha` trong các bản import của `ml_alpha_engine.py`.
2. **Missing Volatility Normalization**: Một số Alpha microstructure chưa được áp dụng `_zscore` triệt để, dẫn đến việc bị lấn át bởi các Alpha có biên độ lớn hơn trong `AlphaEngine`.
3. **Latency Bottleneck**: Mô hình ML (Phi-2) chạy trên CPU đang gây ra độ trễ khoảng 500ms-2s, chưa phù hợp cho các chiến lược Scalping cực nhanh.

---

**KÝ XÁC NHẬN PHÂN TÍCH**: `Antigravity AI Agent (Deep Quantitative Audit Ver 4.8)`
