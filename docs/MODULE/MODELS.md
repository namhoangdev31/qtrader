# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: MODELS (ML WRAPPERS)

**Vị trí**: `qtrader/models/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.21`  
**Trạng thái Audit**: Cảnh báo Thiếu hụt Thành phần (Component Deficit Warning)

---

## 1. HIỆN TRẠNG MODULE

Qua quá trình rà soát, module `qtrader/models` hiện tại đang ở trạng thái **trống/thô sơ (skeleton module)**. Hệ thống chỉ chứa duy nhất một giao diện giao thức (Protocol) mà chưa có bất kỳ mô hình học máy cơ sở nào được đóng gói theo chuẩn.

### Bố cục hiện tại:
- `__init__.py`: Trống (Empty).
- `base.py`: Định nghĩa `Predictor` Protocol.

---

## 2. GIAO THỨC CHUẨN ĐỊNH CHẾ (PREDICTOR PROTOCOL)

Mặc dù thiếu hụt các Implemetation, `qtrader/models/base.py` đã thiết lập một giao thức **`Predictor`** rất chặt chẽ, buộc tất cả các mô hình sau này (XGBoost, LightGBM, CatBoost, Torch, v.v.) phải tuân thủ nghiêm ngặt theo chuẩn Polars:

```python
@runtime_checkable
class Predictor(Protocol):
    def train(self, X: pl.DataFrame, y: pl.Series, params: dict[str, Any] | None = None) -> None:
        ...
    def predict(self, X: pl.DataFrame) -> pl.Series:
        ...
    def save(self, path: str) -> None:
        ...
    def load(self, path: str) -> None:
        ...
```

**Tính năng Thiết kế (Design Protocol):**
1. **Polars-Native**: Đầu vào `X` buộc phải là `pl.DataFrame` thay vì Pandas hay Numpy. Điều này đòi hỏi các Wrapper sau này phải có lớp adapter tự động chuyển đổi Polars thành ma trận tương ứng (`DMatrix` cho XGBoost, `Pool` cho CatBoost).
2. **Persistence**: Bắt buộc phải có `save()` và `load()` để tương thích ngược với hệ thống `mlflow_manager` và `ModelRegistry` trong module `qtrader/ml`.

---

## 3. LỜI KHUYÊN & KẾ HOẠCH BỒI ĐẮP (GAP RESOLUTION)

Dựa trên Quy định Hệ thống (Standash Protocol) tại `01-project-reconnaissance.md`, module này đáng lẽ phải chứa các mô hình cơ sở như `xgboost_wrapper.py` và `torch_model.py`.

Việc hệ thống `qtrader/ml/atomic_trio.py` đang phát triển mạnh về các Foundation Models (TabPFN, Chronos, Phi-2) có thể đã làm mờ nhạt việc sử dụng các mô hình gradient boosting truyền thống. 

**Tuy nhiên, để đóng vòng hệ thống theo chuẩn định chế, CẦN THIẾT PHẢI:**
- Tạo `qtrader/models/xgboost_wrapper.py`: Lớp bọc an toàn tự động nhận vào Polars và train XGBoost.
- Tạo `qtrader/models/catboost_wrapper.py`: Xử lý mượt mà các biến danh mục (categorical features).

**KẾT LUẬN AUDIT**: Module `qtrader/models/` đạt chuẩn về Thiết kế Giao thức (Interface Design) nhưng **Thất bại về mức độ sẵn sàng Báo cáo (Implementation Gap)**. Đội ngũ cần khẩn trương bổ sung các bộ Wrappers cổ điển để hoàn thiện kiến trúc.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Models Audit - Skeleton Detected)`
