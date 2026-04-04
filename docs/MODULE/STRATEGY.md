# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: HỆ THỐNG CHIẾN LƯỢC GIAO DỊCH (STRATEGY)

**Vị trí**: `qtrader/strategy/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.26`  
**Mục tiêu**: Giải phẫu toàn bộ 6 tệp cốt lõi tại tầng Chiến lược (Strategy Layer) — lớp sản sinh Tín hiệu (Signal Generation) nằm giữa lớp Đặc trưng (Features) và lớp Quản lý Lệnh (OMS). Đây là "Bộ não Quyết định" của toàn bộ hệ thống giao dịch.

---

## CẤU TRÚC PHÂN CẤP CHIẾN LƯỢC (3 LỚP)

```
Lớp 3 – META (GOM TÍN HIỆU)     : meta_strategy.py    → Gộp/gia quyền Tín hiệu từ nhiều Strategy
Lớp 2 – ENSEMBLE (TỔ HỢP)       : ensemble_strategy.py → Bầu chọn có Trọng số Động (Meta-Learning)
Lớp 1 – CHIẾN LƯỢC ĐƠN (LEAF)  : momentum.py, probabilistic_strategy.py → Tính Tín hiệu từ Features
Nền tảng – BASE                  : base.py             → Kế toán vị thế + EV + Win-rate
```

---

## 1. FILE: `base.py` (Nền tảng Kế toán Chiến lược - `BaseStrategy`)

**Classes**: `Strategy` (Protocol), `BaseStrategy` (Dataclass)

Đây là lớp bền vững (Persistent Accounting) — mỗi chiến lược kế thừa `BaseStrategy` sẽ có sổ sách giao dịch riêng bằng Polars DataFrame, theo dõi vị thế và đo lường hiệu suất mà không cần giao tiếp với tầng OMS.

* **Protocol `Strategy`**: Giao kèo tối thiểu. Bất kỳ class nào có `compute_signals()` và `on_signal()` đều thỏa mãn interface, không cần kế thừa.
* **Kế toán Vị thế (`on_fill`)**: Nhận `FillEvent` từ broker, ký số lượng cộng dồn (`+qty` nếu BUY, `-qty` nếu SELL) vào dict `_position`. Mỗi fill được lưu vào `fills_log` Polars DataFrame — dữ liệu nền cho tính EV.
* **Kỳ vọng Giá trị (EV Formula)**:
  $$EV = WinRate \times AvgWin - (1 - WinRate) \times |AvgLoss|$$
  Yêu cầu tối thiểu **10 fills** mới tính (tránh bias thống kê nhỏ mẫu). Kết quả phân rã theo từng `symbol` bằng Polars `group_by`.
* **Win-rate Trailing (`win_rate_trailing`)**: Tính từ N lệnh gần nhất (mặc định 100) — chỉ số nhanh để đánh giá sức khỏe chiến lược đang chạy.

---

## 2. FILE: `momentum.py` (Chiến lược Động lượng)

**Classes**: `CrossSectionalMomentum`, `TimeSeriesMomentum`, `MomentumAlpha`

Ba cách triển khai Momentum khác nhau phục vụ 3 mô hình Alpha riêng biệt:

### `CrossSectionalMomentum` (Động lượng Tương đối)
Xếp hạng toàn Vũ trụ tài sản theo Trailing Return rồi Long N tài sản đứng đầu, Short N tài sản đứng cuối. Dùng Polars `.rank(descending=True)` để vector hóa toàn bộ bảng xếp hạng. Cơ chế Skip-Month (`skip_months=1`) loại trừ tháng gần nhất trước khi tính Return (giảm mean-reversion bias ngắn hạn).

### `TimeSeriesMomentum` (Động lượng Tuyệt đối)
Đo sức mạnh xu thế của một tài sản so với chính nó. Công thức cho điểm Tín hiệu:
$$Signal = Sign(TrailingReturn) \times \frac{1}{\sigma_{vol}}$$
> Tức là **Vol-Scaled Momentum**: xu thế mạnh nhưng giai đoạn biến động thấp sẽ cho tín hiệu tuyệt đối lớn hơn. Output được clip vào `[-1.0, +1.0]`.

### `MomentumAlpha` (Nhân tố Alpha Z-Score)
Yếu tố đặc trưng thuần túy (không có logic lệnh). Tính Z-Score của Returns trong cửa sổ rolling:
$$ZScore = \frac{r_t - \mu_{rolling}}{\sigma_{rolling}}$$
Nếu `σ = 0` thì trả về `0.0` (tránh chia cho 0). Đây là input đặc trưng chuẩn hóa dành cho layer ML phía trên.

---

## 3. FILE: `probabilistic_strategy.py` (Chiến lược Xác suất)

**Class chính**: `ProbabilisticStrategy` (kế thừa `BaseStrategy`)

Thay vì quyết định nhị phân BUY/SELL theo ngưỡng cứng (Threshold-Based), chiến lược này xuất ra **Phân phối Xác suất** cho 3 kết quả có thể.

* **Công thức Ánh xạ Tín hiệu → Xác suất**:
  $$P_{buy} = clip\left(\frac{w_{sum} + 1}{2}, 0, 1\right), \quad P_{sell} = 1 - P_{buy}$$
  Ánh xạ không gian $[-1, +1]$ của Weighted Sum sang $[0, 1]$ cho xác suất BUY/SELL.
* **Khử Tự tin (Confidence Shrinkage)**: Xác suất thô được pha loãng về Uniform distribution theo `model_confidence`:
  $$P_{final} = P_{raw} \times conf + \frac{1-conf}{3}$$
  Khi `model_confidence = 1.0` → tin tưởng model 100%. Khi `= 0.5` → pha nửa sang Uniform (bảo thủ hơn).
* **Định cỡ Lệnh Theo Sức thuyết phục**: `on_signal()` tính `position_size = capital × strength × 10%`. Lệnh chỉ phát nếu `strength > 0.1` — chặn Noise trading.
* **Decorator `@require_initialized`**: Bảo vệ `generate_signal()` không chạy nếu chiến lược chưa khởi tạo đủ.

---

## 4. FILE: `ensemble_strategy.py` (Chiến lược Tổ hợp)

**Class chính**: `EnsembleStrategy`

Gom Tín hiệu từ N Chiến lược Con, cân bằng lại Trọng số theo Hiệu suất Gần đây bằng 2 cơ chế song song:

* **Hệ thống Trọng số Kép (Dual-Weight System)**:
  - **Meta-Learning (Ưu tiên)**: Gọi `MetaLearningEngine.get_weights()` lấy trọng số được tính theo 4 chỉ số: `(Sharpe × 0.4) + (PnL_mean × 0.3) + (Drawdown × 0.2) + (HitRatio × 0.1)`.
  - **Legacy Softmax (Fallback)**: Nếu MetaLearning không khả dụng, tự tính trọng số bằng Shifted Softmax rồi clip vào `[min_weight, max_weight]`.
* **Rebalance Định kỳ**: Cứ mỗi `rebalance_frequency` tín hiệu, gọi `_rebalance_weights()` điều chỉnh trọng số.
* **Gộp Tín hiệu (`_combine_signals`)**: Tính xác suất kết hợp bằng Weighted Sum xác suất của 3 loại (BUY/SELL/HOLD). Sức mạnh tín hiệu là độ lệch so với Uniform:
  $$Strength = max(P_{buy}, P_{sell}, P_{hold}) - \frac{1}{3}$$
* **Cập nhật Regime**: `update_regime_info()` truyền thông tin `(regime, confidence)` từ `RegimeDetector` xuống `MetaLearningEngine`, cho phép trọng số thích nghi theo điều kiện thị trường.

---

## 5. FILE: `meta_strategy.py` (Tầng Meta Gộp Tín hiệu)

**Classes**: `MetaStrategy` (ABC), `WeightedMetaStrategy`, `RegimeAwareMetaStrategy`

Lớp trừu tượng điều phối nhiều chiến lược đơn lên một Tín hiệu Thống nhất. Triển khai 2 biến thể:

### `WeightedMetaStrategy` (Biểu quyết Có Trọng số)
Ánh xạ tín hiệu sang số: `{BUY: +1, SELL: -1, HOLD: 0}`. Tính tổng có trọng số:
$$Score = \sum_i w_i \times Signal_i \times Strength_i$$
Áp lệnh cuối theo ngưỡng cứng: `Score > 0.5 → BUY`, `Score < -0.5 → SELL`, `else → HOLD`.

### `RegimeAwareMetaStrategy` (Nhận thức Chế độ Thị trường)
Sử dụng `RegimeDetector.current_regime_confidence()` để xác định chế độ thị trường (`regime_id ∈ {0, 1, 2}`) và áp **trọng số Regime-Specific** cho từng chiến lược con. Khi Detector thất bại → rơi xuống `default_weights`. Đảm bảo hệ thống không sập dù ML phần dưới lỗi.

* **Kiểm tra An toàn (`_validate_signals`)**: Đảm bảo tất cả Tín hiệu cùng `symbol` và trong tập `{BUY, SELL, HOLD}` — cổng kiểm soát chất lượng đầu vào.

---

**KẾT LUẬN AUDIT**: `qtrader/strategy` xây dựng kiến trúc 3 tầng Tín hiệu rất bài bản theo mô hình **Leaf (Chiến lược Đơn) → Ensemble (Gộp Động) → Meta (Cổng Lọc Trọng số)**. Điểm ưu tú nhất là cơ chế **khử tự tin Bayesian** trong `ProbabilisticStrategy` (Confidence Shrinkage về Uniform) và vòng phản hồi học máy trong `EnsembleStrategy` (Meta-Learning Weight Adaptation theo Regime). Kiến trúc này đảm bảo hệ thống không bao giờ "chắc chắn 100%" trong điều kiện uncertain, tuân thủ đúng triết lý quản lý rủi ro Định lượng.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Strategy Layer File-by-File Deep Audit — Verified)`
