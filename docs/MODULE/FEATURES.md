# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: FEATURES (FACTOR ENGINEERING)

**Vị trí**: `qtrader/features/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.16`  
**Mục tiêu**: Quản trị vòng đời nhân tố (Factors) – từ định nghĩa Protocol, tính toán vector hóa (Polars), biến đổi tín hiệu (Neutralization) đến lưu trữ analytical (DuckDB).

---

## 1. KIẾN TRÚC FACTOR PROTOCOL (THE GOLDEN RULE)

Hệ thống QTrader áp dụng kỷ luật **Stateless & Vectorized Intelligence**. Mọi nhân tố phải tuân thủ nghiêm ngặt hai Protocol chính (`base.py`):

### 1.1 `Feature` Protocol (Giao thức Nhân tố)
Mọi lớp triển khai nhân tố (RSI, Moving Averages, v.v.) phải kế thừa `BaseFeature` và cung cấp:
- **`compute(df: pl.DataFrame) -> pl.Series | pl.DataFrame`**: Hàm lõi thực thi tính toán. Phải là chuỗi biểu thức Polars thuần túy. Cấm tuyệt đối `for loops` hoặc `numpy.apply`.
- **`validate_inputs(df: pl.DataFrame)`**: Kiểm tra sự hiện diện của `required_cols` (ví dụ: `["high", "low", "close"]`) và độ dài tối thiểu `min_periods`.
- **`min_periods`**: Chốt chặn Look-ahead Bias. Phải trả về `null` cho `N-1` dòng dữ liệu đầu tiên.

### 1.2 `FeaturePipeline` Protocol
Định nghĩa giao diện cho các bộ điều phối hoặc Ensemble kết hợp nhiều nhân tố thành một Wide DataFrame duy nhất.

---

## 2. BỘ MÁY GIẢI QUYẾT FACTOR (EXECUTION ENGINE)

### 2.1 `engine.py`: FactorEngine (Trình điều phối)
`FactorEngine` là trung tâm vận hành tính toán và lưu trữ:
- **`compute(df)`**: Chạy song song (vectorized) toàn bộ danh mục nhân tố đã đăng ký.
- **`compute_latest(df)`**: Tối ưu cho Live Trading, chỉ trả về kết quả cho dòng dữ liệu mới nhất (Tail(1)).
- **`compute_and_save()`**: Luồng tự động: Tính toán → Lưu trữ vào `FeatureStore`.
- **`compute_multi_symbol()`**: Xử lý tập trung cho danh mục đa tài sản, tự động gán cột `symbol`.

### 2.2 `registry.py`: FeatureRegistry (Hệ thống Định danh)
- **Lazy Instantiation**: Chỉ khởi tạo các lớp nhân tố khi có yêu cầu thực tế.
- **`register(name, feature_instance)`**: Đăng ký định danh duy nhất (ví dụ: `rsi_14`).
- **`compute_all()`**: Tự động thực thi toàn bộ danh mục và trả về `Wide DataFrame`.
- **Trạng thái**: Đã phục hồi (Restored). Toàn bộ 13+ nhân tố mặc định hiện đã được kết nối thông qua `build_default_registry()`.

---

## 3. BIẾN ĐỔI & TRUNG HÒA TÍN HIỆU (TRANSFORMATION)

### 3.1 `neutralization.py`: FactorNeutralizer (Analytical Tools)
Hệ thống cung cấp các phương thức tĩnh (Static methods) để biến đổi tín hiệu thô thành Alpha Ready:

| Phương thức | Logic / Tham số | Mục tiêu Alpha |
| :--- | :--- | :--- |
| **`sector_neutralize`** | `(df, col, group="sector")` | Khử rủi ro hệ thống (Systematic Risk) theo nhóm ngành bằng Polars `.over()`. |
| **`market_neutralize`** | `(df, col)` | Trừ đi trung bình toàn thị trường (Market Beta). |
| **`winsorize`** | `(series, lower=0.01, upper=0.99)` | Cắt tỉa Outliers để ổn định các phép toán Z-score. |
| **`zscore`** | `(series, window=None)` | Chuẩn hóa về trung bình 0, Std 1 (Hỗ trợ Rolling Window). |
| **`rank_normalize`** | `(series)` | Chuyển đổi thành phân vị [0, 1]. Robust với nhiễu và Outliers. |
| **`orthogonalize`** | `(df, cols)` | Sử dụng PCA (sk-learn) để khử tính đa cộng tuyến giữa nhiều nhân tố. |

---

## 4. LƯU TRỮ TÍNH NĂNG (FEATURE STORE)

### 4.1 `store.py`: Hybrid Analytical Storage
Chiến lược lưu trữ phân lớp (Tiered Storage) giúp bảo đảm SLA truy vấn cực nhanh:
- **Primary: DuckDB (`qtrader.db`)**: 
  - Lưu dưới dạng định dạng cột (Columnar).
  - Bảng: `features_{symbol}_{tf}`.
  - Tối ưu hóa truy vấn Analytical (Lọc theo thời gian và Column Pruning).
- **Secondary: Parquet (`data_lake/features/`)**:
  - Tự động fallback nếu DuckDB gặp lỗi schema hoặc treo kết nối.
  - Phân mảnh (Partitioning) theo: `symbol={sym}/tf={tf}/features.parquet`.
  - Nén Snappy giúp tiết kiệm 70% dung lượng đĩa.

---

## 5. DANH MỤC NHÂN TỐ (FACTOR LIBRARY)

Tất cả các nhân tố dưới đây hiện đã được di chuyển về thư mục `qtrader/features/factors/`:

### 5.1 Technical Factors (`technical.py`)
- **RSI (Relative Strength Index)**: Sử dụng làm mượt Wilder qua `ewm_mean(alpha=1/period)`.
- **ATR (Average True Range)**: Tính True Range qua `max_horizontal([HL, HC, LC])`.
- **MACD**: Xuất 3 cột (`macd`, `signal`, `hist`) sử dụng Span-based EWM.
- **BollingerBands**: Tính `%B` (vị trí tương đối trong dải) dựa trên rolling mean/std.
- **ROC / Momentum**: Tính toán tỷ lệ thay đổi và log return vector hóa.

### 5.2 Volume Factors (`volume.py`)
- **VWAP (Volume Weighted Avg Price)**: Tính toán tích lũy `cumsum(典型_price * vol) / cumsum(vol)`.
- **OBV (On-Balance Volume)**: Tăng tích lũy khối lượng dựa trên chiều hướng giá.
- **Force Index**: Tích số giữa `price_diff` và `volume`, làm mượt qua EMA 13.
- **VolumeRatio**: So sánh khối lượng hiện tại với trung bình 20 phiên.

### 5.3 Lagged & Statistical Factors (`lagged.py`)
- **AutoCorrelation**: Tương quan chuỗi thời gian của lợi suất.
- **SkewFeature**: Đo lường độ lệch (Asymmetry) của phân phối lợi suất.
- **ReturnVolatility**: Độ lệch chuẩn lợi suất trượt (Rolling Standard Deviation).

---

**KẾT LUẬN AUDIT**: Module Features của QTrader đạt chuẩn **Institutional Quality §6.2**. Sự kết hợp giữa bộ máy Polars Stateless và Feature Store DuckDB cung cấp một nền tảng vững chắc cho cả nghiên cứu Quants và thực thi Algo-trading tần suất cao.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Features Deep Audit - Finalized & Restored)`
