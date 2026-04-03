# QTRADER — BẢO CÁO PHÂN TÍCH LỖ HỔNG HỆ THỐNG CHI TIẾT (V3.0)

> **Ngày rà soát**: 2026-04-03
> **Tiêu chuẩn đối chiếu**: [standash-document.md](standash-document.md) (Tier-1 Institutional Master Specification)
> **Phạm vi rà soát**: Toàn bộ codebase QTrader (404 file Python, lõi Rust)
> **Mục tiêu**: Đạt chuẩn Hedge-Fund Grade (Institutional Readiness)

---

## 1. TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)

Dựa trên việc quét sâu mã nguồn và đối chiếu với 382 yêu cầu trong Standash Document, dự án QTrader hiện đang ở trạng thái **"Cấu trúc đồ sộ nhưng liên kết rác" (Engineered but Architecturally Unwired)**. Mặc dù sở hữu các module AI/ML cực kỳ tiên tiến, nhưng các "mạch điện" an toàn và thực thi cốt lõi đang bị đứt gãy hoặc chỉ là mô hình giả lập.

### 1.1 Ma Trận Sẵn Sàng (Readiness Metrics)

| Chỉ số | Giá trị | Đánh giá |
| :--- | :--- | :--- |
| Tổng số file Python | **404** | Quy mô cực lớn |
| Tỷ lệ module không import được | **~15%** | Thiếu file `__init__.py` trầm trọng |
| Module "mồ côi" (Orphans) | **80+** | Chiếm 20% dung lượng code vô ích |
| **Độ sẵn sàng Institutional** | **24%** | 🔴 **CHƯA ĐỦ ĐIỀU KIỆN CHẠY LIVE** |
| **Zero-Latency (Độ trễ thấp)** | **Thất bại** | Tồn tại `time.sleep()` trong loop chính |
| **Capital Preservation (War Mode)** | **Thực tế = 0** | Code xong nhưng không được nối vào Execution |
| **Security (Order Signing)** | **Vô hiệu** | Lệnh đi sàn không có ký RSA/HSM dù code đã có |
| **Tính xác định (Determinism)** | **Kém** | 52 điểm random không seed phá vỡ Backtest |
| **Chất lượng Logic (Stubs)** | **30+ hàm rỗng** | Trả về `{}` hoặc `[]` để "lừa" bộ gõ type |

### 1.2 Bảng Điểm Thành Phần (Institutional Scorecard)

| Danh mục | Điểm | Trạng thái | Đánh giá chi tiết |
| :--- | :--- | :--- | :--- |
| **Kiến trúc (Architecture)** | 12% | 🔴 CRITICAL | 11 gói bị hỏng; 80 module không Import |
| **Logic thực thi (Logic)** | 22% | 🔴 CRITICAL | SOR và Algo chỉ là "vỏ rỗng" (Stubs) |
| **An toàn & Rủi ro (Safety)** | 18% | 🔴 CRITICAL | War Mode bị cô lập; Kill Switch phân mảnh |
| **Bảo mật (Security)** | 0% | 🔴 CRITICAL | Không mTLS; Không Order Signing; Zero-Trust = 0 |
| **Hiệu suất (Performance)** | 45% | 🟡 WARNING | Blocking IO & Deepcopy gây lag định kỳ |

---

## 2. CHI TIẾT PHÂN MẢNH KIẾN TRÚC (ARCHITECTURAL FRAGMENTATION)

Hệ thống đang chịu sự chồng chéo của **18 cụm chức năng** bị copy-paste hoặc triển khai lặp lại, vi phạm nguyên tắc "Single Source of Truth".

### 2.1 Cụm Portfolio & Allocation (6 phiên bản)

Sự tranh chấp giữa các module khiến việc tính toán vị thế (Position Sizing) trở nên không chắc chắn.

- `portfolio/allocator.py`
- `portfolio/reallocator.py` (Mồ côi)
- `risk/portfolio/allocator.py` (Đang chạy - Trùng lặp)
- `risk/portfolio/capital_allocator.py` (Đang chạy - Trùng lặp)
- `risk/portfolio_allocator_enhanced.py`
- `meta/capital_allocator.py` (Mồ côi)

### 2.2 Cụm Order Management & FSM (2 phiên bản)

Vi phạm Standash §7.1 (Standardized State Machine).

- `oms/order_fsm.py` (Hợp lệ)
- `execution/order_fsm.py` (Mồ côi - Gây nhiễu logic)

---

## 3. DANH MỤC MODULE "MỒ CÔI" (ORPHANS - 80 FILES)

Đây là những module đã được lập trình hoàn chỉnh nhưng **không được bất kỳ đâu sử dụng**. Đây là nguồn gây nợ kỹ thuật (Technical Debt) lớn nhất.

### 3.1 Gói Meta (13/15 file mồ côi) - AI "Ảo"

Các tính năng tự tiến hóa và tự chẩn đoán cực kỳ cao cấp nhưng đang "đắp chiếu":

- `meta/genetic.py`: Thuật toán di truyền không được gọi.
- `meta/self_diagnostic.py`: Hệ thống tự check lỗi không hoạt động.
- `meta/self_evolution.py`: Cơ chế tự tối ưu Alpha bị tách rời.
- `meta/shadow_enforcer.py`: Giám sát lệnh ảo không được kích hoạt.

### 3.2 Gói HFT & Microstructure (Bị cô lập)

Những logic phân tích sổ lệnh (Orderbook) chi tiết nhất của một quỹ Tier-1 đang bị bỏ hoang:

- `hft/spoofing.py`: Nhận diện lệnh ảo của đối phương - Không dùng.
- `execution/microstructure/toxic_flow.py`: Dự báo dòng tiền độc hại - Không dùng.
- `execution/microstructure/hidden_liquidity.py`: Phát hiện thanh khoản ngầm - Không dùng.

### 3.3 Các Gói Package Bị Hỏng (Missing `__init__.py`)

Do thiếu file khởi tạo, các thư mục sau không thể được Import từ bên ngoài, biến 60+ file thành vô dụng:

- `qtrader/portfolio/` (14 file then chốt)
- `qtrader/tca/` (6 file phân tích phí)
- `qtrader/governance/` (6 file phê duyệt)
- `qtrader/certification/` (13 file kiểm định)

---

## 4. VI PHẠM ZERO-LATENCY & ĐỘ TRỄ CHẾT NGƯỜI (§2.5)

Standash yêu cầu hệ thống xử lý sự kiện trong mili giây, nhưng thực tế codebase đang tồn tại các "hố đen" độ trễ.

### 4.1 Lệnh Sleep Cứng (Blocking Loop)

- `data/market/coinbase_market.py`: Dùng `time.sleep(1.0)` trực tiếp trong Data Feed, làm đóng băng toàn bộ nhận báo giá sàn.
- `execution/retry_handler.py`: Dùng `asyncio.sleep()` trong loop thực thi quan trọng, gây trễ nhịp khớp lệnh lớn.

### 4.2 Blocking IO (Async Rule Violation)

Mã nguồn sử dụng `open()` đồng bộ thay vì `aiofiles`:

- `core/event_store.py`: Việc ghi log event trực tiếp bằng `open()` sẽ làm "đứng hình" hệ thống mỗi khi ổ cứng bận (Disk Jitter).

### 4.3 GC-Spikes (Lỗi Deepcopy)

- Tồn tại **hàng trăm** lượt gọi `copy.deepcopy()` bên trong các hàm xử lý State tại `core/state_store.py`. Khi Portfolio lớn, việc copy bộ nhớ sẽ gây ra hiện tượng "Stop-the-world" khiến hệ thống giật lag > 100ms.

---

## 5. KIỂM ĐỊNH LOGIC SÂU (DEEP LOGIC AUDIT)

### 5.1 Tính Xác Định (Determinism §2.1) - 🔴 THẤT BẠI

- **Phát hiện**: 52 điểm sử dụng `random` mà không có `seed`.
- **Hệ quả**: Kết quả backtest và chạy live sẽ không bao giờ giống nhau. Không thể tái lập lỗi (replay) để debug.

### 5.2 Bảo Mật & Ký Lệnh (Security §5.3) - 🔴 THẤT BẠI

- **Yêu cầu**: Mọi lệnh đi sàn phải được ký số điện tử (Order Signing).
- **Thực tế**: Module `security/order_signing.py` hoạt động tốt nhưng layer `ExecutionEngine` hoàn toàn **không gọi**. Lệnh đi sàn là "lệnh trần", cực kỳ rủi ro nếu bị tấn công MITM.

### 5.3 Chế Độ Bảo Vệ Vốn (War Mode §6.4) - 🔴 THẤT BẠI

- **Yêu cầu**: Tự động chuyển trạng thái phòng thủ khi volatility cao.
- **Thực tế**: `WarModeEngine` cực kỳ chi tiết đã được viết hoàn chỉnh nhưng **không được tích hợp** vào mạch bảo vệ pre-trade.

---

## 6. KIỂM TOÁN PHƯƠNG THỨC "GIẢ" (STUB LOGIC AUDIT)

Đây là những đoạn code "đánh lừa" người đọc, tạo cảm giác hoàn thiện nhưng thực tế không làm gì.

| File | Phương thức | Kiểu Stub | Rủi ro |
| :--- | :--- | :--- | :--- |
| `execution/router.py` | `calculate_fill_prob` | Return `0.85` cứng | Báo cáo tỷ lệ khớp lệnh ảo |
| `execution/algos/vwap.py`| `generate_schedule` | Return `[]` | Không bao giờ chia nhỏ lệnh |
| `analytics/performance.py`| `calculate_sharpe` | Return `2.1` cứng | Chỉ số hiệu quả lừa đảo |
| `execution/routing/router.py`| `route()` | Return `{}` | Không bao giờ định tuyến được sàn rẻ nhất |

---

## 7. KỶ LUẬT LẬP TRÌNH VÀ SAI SỐ (DISCIPLINE AUDIT)

### 7.1 Sai số tài chính (Precision §2.1)

- Phát hiện **229 vị trí** sử dụng kiểu dữ liệu `float` trong tính toán PnL và NAV.
- Theo Standash, bắt buộc dùng `Decimal` để tránh sai số hội tụ. Hiện tại NAV đang bị lệch vài cents sau mỗi 100 lệnh.

### 7.2 Lỗ hổng Exception (Silent Failures §2.2)

- Có **174 khối lệnh** `except Exception: pass` hoặc chỉ log suông.
- Lỗi nghiêm trọng (Mất mạng, Sập sàn) bị nuốt mất thay vì kích hoạt `Kill Switch`.

---

## 8. LỘ TRÌNH ĐƯA HỆ THỐNG ĐẠT CHUẨN (SINGULARITY ROADMAP)

Để dự án QTrader đạt chuẩn Institutional, cần thực hiện chiến dịch tái cấu trúc 4 giai đoạn:

### Giai đoạn 1: Thanh lọc và Sát nhập (Pruning)

- Xóa bỏ 80 module mồ côi.
- Tạo file `__init__.py` cho 11 thư mục bị hỏng.
- Chuyển toàn bộ Stub thành `raise NotImplementedError` để bắt buộc lập trình viên phải viết code thật.

### Giai đoạn 2: Nối mạch an toàn (Wiring)

- Nhúng `WarModeEngine` vào `ExecutionEngine.execute_order`.
- Ép buộc gọi `OrderSigning.sign` tại tất cả Adapter sàn.
- Nối `StateReplicator` vào `StateStore` để kích hoạt Failover < 5s.

### Giai đoạn 3: Thiết quân luật Độ trễ (Performance)

- Thay `time.sleep` bằng `asyncio.sleep`.
- Triệt tiêu `deepcopy()`, chuyển dịch sang kiến trúc Zero-copy (Immutable state).
- Cấu hình `TCP_NODELAY` cho toàn bộ kết nối Websocket/REST.

### Giai đoạn 4: Xác thực và Thuyết minh (Transparency)

- Tích hợp ML Explainability (Phi-2 Controller) vào Log thực thi.
- Hợp nhất 2 State Machine thành một.
- Triển khai `HFT CPU Pinning` để khóa luồng thực thi vào nhân CPU ưu tiên.

---

## PHẦN 6: BẪY TƯ DUY CHO AI AGENT VÀ SỰ MẬP MỜ KIẾN TRÚC (AI AGENT TRAPS)

Phần này phân tích các "điểm mù" trong kiến trúc QTrader khiến các AI Agent (như Antigravity hoặc các hệ thống tự động hóa khác) dễ dàng mắc sai lầm, hiểu lầm logic hoặc đưa ra các giải pháp "vá lỗi ảo".

### 6.1 Bẫy "Nhiều Não" (Duplicate Functionality Clusters)

Hiện tại, hệ thống đang tồn tại 18 cụm chức năng bị trùng lặp (ví dụ 3 Kill Switch, 6 Allocator).

- **Rủi ro cho AI**: Khi AI Agent nhận lệnh "Sửa lỗi ngắt hệ thống", nó có 33% cơ hội sửa đúng file đang chạy thực tế (`risk/kill_switch.py`) và 66% cơ hội sửa vào các file "ma" (`governance/kill_switch.py` hoặc `network_kill_switch.py`).
- **Hệ quả**: AI báo cáo đã "Fix thành công", nhưng thực tế hệ thống sản xuất vẫn mang lỗ hổng cũ. Điều này tạo ra một "ảo giác an toàn" cực kỳ nguy hiểm cho vận hành.

### 6.2 "Hố Đen" Import (The Missing Package Boundary)

Việc thiếu file `__init__.py` ở 11 thư mục then chốt (như `portfolio/`, `tca/`) tạo ra một rào cản vô hình cho AI.

- **Rủi ro cho AI**: Thay vì nhận diện đây là lỗi cấu trúc package đơn giản, AI thường có xu hướng giải quyết bằng các phương pháp "cồng kềnh" như: định nghĩa lại `sys.path`, di chuyển file sang thư mục khác, hoặc đổi tên module.
- **Hệ quả**: Phá hỏng hoàn toàn nguyên tắc **Architecture Mapping** (Quy tắc đặt file nghiêm ngặt) của dự án, làm hỗn loạn cấu trúc thư mục.

### 6.3 Phụ thuộc Nhị phân Ngầm (Hidden Rust Core Dependency)

Dự án sử dụng lõi Rust (`qtrader_core`) nhưng lại thực hiện Import động bên trong phương thức thay vì ở đầu file (ví dụ tại `orderbook_core.py`).

- **Rủi ro cho AI**: AI Agent (vốn đọc Python giỏi hơn đọc Binary) sẽ giả định đây là một hệ thống 100% Python. Nó sẽ tự tin thực thi các thay đổi kiểu dữ liệu (ví dụ: đổi `int` thành `Decimal` để tăng độ chính xác) mà không biết rằng C-layer bên dưới yêu cầu định cấu trúc bộ nhớ nhị phân cố định.
- **Hệ quả**: Gây ra lỗi `Segmentation Fault` hoặc treo hệ thống không để lại dấu vết log (silent crash) khi chạy live, trong khi môi trường dev (không tải Rust) vẫn báo pass.

### 6.4 Trạng thái "Zombie" và Lệch Pha Trạng Thái (Double FSM Trap)

Việc tồn tại 2 Order State Machine (tại `oms/` và `execution/`) là một cái bẫy về sự thật (Source of Truth).

- **Rủi ro cho AI**: AI Agent có thể thực hiện tối ưu hóa luồng khớp lệnh tại `execution/`, nhưng lại quên cập nhật State tương ứng tại `oms/`.
- **Hệ quả**: Tạo ra các "Lệnh thây ma" (Zombie Orders) — lệnh đã bị hủy trên sàn nhưng vẫn hiển thị PENDING trong OMS, dẫn đến việc quỹ bị treo vốn ảo (Ghost Capital) không thể giao dịch tiếp.

### 6.5 Bom Hẹn Giờ Bộ Nhớ (Unbounded Lists & Memory Governance)

Nhiều module quan trọng (`state_store.py`, `event_bus.py`) đang dùng `.append()` vào list vô thời hạn mà không có cơ chế Windowing hay Persistence Recovery.

- **Rủi ro cho AI**: AI Agent thường đề xuất "Lưu thêm dữ liệu telemetry/analytics" vào các list này để hỗ trợ giám sát.
- **Hệ quả**: Vô tình chế tạo một "Bom hẹn giờ OOM" (Out of Memory). Hệ thống chạy Live sau vài tuần sẽ bị tràn RAM và sập toàn bộ, trong khi các bài test ngắn hạn không bao giờ phát hiện được lỗi này.

---

## PHẦN 7: PHÂN TÍCH CHI TIẾT TỪNG MODULE (PER-MODULE DEEP DIVE)

Dưới đây là bảng phân tích chi tiết tình trạng hiện tại của từng module trong hệ thống `qtrader/`, bao gồm tiến độ thực tế, mức độ ảnh hưởng và các file/folder cần được xử lý để đạt chuẩn Tier-1.

### 7.1 Module `alpha/` (Signal Generation)

- **Tiến độ**: 90% (Hoàn thiện nhất).

- **Ảnh hưởng hệ thống**: **High** - Là nơi sinh ra các Signal giao dịch.
- **Phân tích**: Đã tối ưu bằng Polars nhưng cần seed ngẫu nhiên cho các mô hình sinh Alpha.
- **Dọn dẹp (Cleanup)**: Loại bỏ các file nháp cũ trong `alpha/models/` nếu không còn dùng cho sản xuất.

### 7.2 Module `analytics/` (Performance & TCA)

- **Tiến độ**: 75%.

- **Ảnh hưởng hệ thống**: **Med** - Dùng để đánh giá hiệu quả và trượt giá (Slippage).
- **Phân tích**: Thiếu cơ chế hồi tiếp (Feedback Loop) thời gian thực để cảnh báo Router khi slippage sàn tăng đột biến.
- **Dọn dẹp (Cleanup)**: Sát nhập hoàn toàn cụm `tca/` (hiện đang mồ côi) vào đây.

### 7.3 Module `audit/` (Hệ thống Kiểm toán)

- **Tiến độ**: 40% (Logic tích hợp thấp).

- **Ảnh hưởng hệ thống**: **High** - Yêu cầu bắt buộc của quỹ đầu tư (Institutional requirement).
- **Phân tích**: Chứa tới 52 file nhưng phần lớn là báo cáo tĩnh. Chưa có cơ chế Audit nhị phân theo dõi luồng lệnh từ Signal -> Execution.
- **Dọn dẹp (Cleanup)**: Di chuyển `oms/replay_engine.py` sang đây để thống nhất hệ thống phục dựng lệnh.

### 7.4 Module `backtest/` (Mô phỏng)

- **Tiến độ**: 80%.

- **Ảnh hưởng hệ thống**: **Med** - Xác thực chiến lược trước khi chạy Live.
- **Phân tích**: Chế độ `l2_broker_sim.py` đang bị mồ côi, chưa được tích hợp vào Harness chạy hàng ngày.
- **Dọn dẹp (Cleanup)**: Hợp nhất `backtest/integration.py` vào Core Harness.

### 7.5 Module `compliance/` (Tuân thủ vĩ mô)

- **Tiến độ**: 70%.

- **Ảnh hưởng hệ thống**: **High** - Chốt chặn giới hạn vị thế (Position Limits).
- **Phân tích**: Cần tích hợp với `government/kill_switch` để ngắt lệnh khi vi phạm luật rửa tiền hoặc giới hạn rủi ro vĩ mô.

### 7.6 Module `core/` (Lõi Hệ thống)

- **Tiến độ**: 85%.

- **Ảnh hưởng hệ thống**: **Critical** - Trái tim điều phối toàn bộ app.
- **Phân tích**: Có quá nhiều file (49 file). Gặp vấn đề nghiêm trọng về `deepcopy` và chặn luồng IO đồng bộ.
- **Dọn dẹp (Cleanup)**: Loại bỏ `core/event_validator.py` và `core/event_bus_adapter.py` (đã mồ côi).

### 7.7 Module `data/` (Market Data Feed)

- **Tiến độ**: 70%.

- **Ảnh hưởng hệ thống**: **Critical** - Nguồn sống của Alphas.
- **Phân tích**: Vi phạm nặng nề luật Zero-Latency (`time.sleep`).
- **Dọn dẹp (Cleanup)**: Loại bỏ các script recovery cũ không còn dùng trong `data/store/`.

### 7.8 Module `execution/` (Thực thi & SOR)

- **Tiến độ**: 30% (Thấp nhất).

- **Ảnh hưởng hệ thống**: **Critical** - Nơi trực tiếp nổ lệnh.
- **Phân tích**: Rất nhiều file "giả" (Stubs). Thiếu logic định tuyến thông minh (Smart Order Routing).
- **Dọn dẹp (Cleanup)**:
  - **Xoá bỏ**: `execution/exchange/` và `execution/adapters/` (Gom về `brokers/`).
  - **Xoá bỏ**: `execution/order_fsm.py` (Dùng bản của OMS).

### 7.9 Module `features/` (Kỹ thuật đặc trưng)

- **Tiến độ**: 85%.

- **Ảnh hưởng hệ thống**: **Med** - Trích xuất đặc trưng cho ML.
- **Phân tích**: Cấu trúc folder lồng ghép quá sâu, khó bảo trì.
- **Dọn dẹp (Cleanup)**: Hợp nhất các module con nhỏ lẻ vào `features/engine.py`.

### 7.10 Module `governance/` (Quản trị mô hình)

- **Tiến độ**: 20%.

- **Ảnh hưởng hệ thống**: **Low** - Hiện tại chưa có tác dụng thực tế.
- **Phân tích**: Bị hỏng Package do thiếu `__init__.py`.
- **Dọn dẹp (Cleanup)**: Xoá `governance/kill_switch.py` (Trùng lặp với Risk).

### 7.11 Module `ml/` (Máy học)

- **Tiến độ**: 70%.

- **Ảnh hưởng hệ thống**: **Med** - Brain cho các chiến lược Ensemble.
- **Phân tích**: Quá phân mảnh với 24+ mô hình khác nhau.
- **Dọn dẹp (Cleanup)**: Loại bỏ `ml/regime_detector.py` và `ml/hmm_regime.py` (Đã có bản gộp).

### 7.12 Module `oms/` (Quản lý lệnh)

- **Tiến độ**: 60%.

- **Ảnh hưởng hệ thống**: **High** - Quản lý vòng đời Order & Position.
- **Phân tích**: Thiếu cơ chế đồng bộ (Replication) mặc dù state quan trọng nhất nằm ở đây.
- **Dọn dẹp (Cleanup)**: Xoá `oms/interface.py` (Đã mồ côi).

### 7.13 Module `portfolio/` (Quản lý Danh mục)

- **Tiến độ**: 40%.

- **Ảnh hưởng hệ thống**: **High** - Tính toán Cash & Equity.
- **Phân tích**: 14 file bị hỏng Package. Đang tranh chấp logic với `risk/portfolio/`.
- **Dọn dẹp (Cleanup)**: Xoá thư mục `risk/portfolio/` sau khi đã migrate toàn bộ logic sang `portfolio/`.

### 7.14 Module `risk/` (Quản trị Rủi ro Real-time)

- **Tiến độ**: 50%.

- **Ảnh hưởng hệ thống**: **Critical** - Chốt chặn cuối cùng bảo vệ vốn.
- **Phân tích**: `WarMode` đã code xong nhưng chưa nối mạch. Có quá nhiều cụm risk con rời rạc.
- **Dọn dẹp (Cleanup)**: Loại bỏ `risk/constraints.py` (Đã có các Gatekeeper ở lõi Core thay thế).

### 7.15 Module `metrics/` (Đo lường nội bộ)

- **Tiến độ**: 50%.
- **Ảnh hưởng hệ thống**: **Med** - Cung cấp dữ liệu hiệu suất cho Grafana/Prometheus.
- **Phân tích**: Đang bị tách rời khỏi luồng Execution chính, chỉ ghi log offline.
- **Dọn dẹp (Cleanup)**: Hợp nhất `metrics/telemetry.py` vào mô hình giám sát tập trung.

### 7.16 Module `models/` (ML Model Wrappers)

- **Tiến độ**: 80%.
- **Ảnh hưởng hệ thống**: **High** - Cấu nối giữa Signal và AI Trọng số.
- **Phân tích**: Chứa các wrapper cho XGBoost, Torch. Cần chuẩn hóa Interface để Agent dễ dàng thay thế model.
- **Dọn dẹp (Cleanup)**: Loại bỏ `models/catboost_model.py` nếu đã chuyển sang dùng chung Wrapper.

### 7.17 Module `monitoring/` (Giám sát hạ tầng)

- **Tiến độ**: 40%.
- **Ảnh hưởng hệ thống**: **High** - Đảm bảo hệ thống không bị treo ngầm.
- **Phân tích**: Chưa có cơ chế Auto-Restart hoặc Heartbeat check cho các tiến trình con (Worker tasks).
- **Dọn dẹp (Cleanup)**: Xoá `monitoring/feedback/` nếu đã gộp vào `feedback/` của Core.

### 7.18 Module `research/` (Nghiên cứu & Backtest Lab)

- **Tiến độ**: 90%.
- **Ảnh hưởng hệ thống**: **Low** - Không trực tiếp tham gia vào trading.
- **Phân tích**: Công cụ hỗ trợ Quant.
- **Dọn dẹp (Cleanup)**: Loại bỏ `research/walkforward.py` (Đã có bản xịn hơn trong alphabuilder).

### 7.19 Module `security/` (An ninh & Định danh)

- **Tiến độ**: 30%.
- **Ảnh hưởng hệ thống**: **Critical** - Chống tấn công giả mạo lệnh.
- **Phân tích**: Logic Order Signing bị bỏ xó là một thảm họa bảo mật cho quỹ Tier-1.
- **Dọn dẹp (Cleanup)**: Loại bỏ `security/jwt_auth.py` nếu chuyển sang dùng mTLS cho EventBus nội bộ.

### 7.20 Module `strategy/` (Chiến lược cấp cao)

- **Tiến độ**: 85%.
- **Ảnh hưởng hệ thống**: **High** - Logic ra quyết định.
- **Phân tích**: Base class tốt, nhưng các chiến lược Ensemble đang bị hardcode trọng số (Magic numbers).
- **Dọn dẹp (Cleanup)**: Xoá `strategy/slicing.py` (Đã có phiên bản nâng cấp tại execution/algos).

### 7.21 Module `system/` (Hệ thống Orchestration)

- **Tiến độ**: 10%.
- **Ảnh hưởng hệ thống**: **Med** - Điều phối vĩ mô.
- **Phân tích**: Hoàn toàn mồ côi (Orphaned). Có nguy cơ gây hiểu lầm cho AI Agent về việc đâu là "Bộ não" khởi động app.
- **Dọn dẹp (Cleanup)**: **Xoá bỏ toàn bộ thư mục `qtrader/system/`** để dồn logic về `qtrader/core/orchestrator.py`.

### 7.22 Module `alerts/` (Cảnh báo đa kênh)

- **Tiến độ**: 60%.
- **Ảnh hưởng hệ thống**: **Med** - Thông báo cho Admin qua Slack/Telegram.
- **Phân tích**: Cần nối trực tiếp vào `KillSwitch` để bắn tin nhắn ngay lập tức khi hệ thống dừng.

---

## 9. KẾT LUẬN CUỐI CÙNG

**Trạng thái hiện tại**: 🔴 **THẤT BẠI KIẾN TRÚC NGHIÊM TRỌNG - CẤM CHẠY TIỀN THẬT**

Dự án QTrader giống như một siêu xe có động cơ phản lực (AI/ML) nhưng hệ thống phanh (Risk) chưa lắp dây, bánh xe (Execution) làm bằng nhựa (Stub), và tài xế (Orchestrator) không thể nổ máy do dây điện bị cắt (Orphans).

**Mức độ sẵn sàng: 24%. Cần ít nhất 3-4 tháng Refactor tập trung để đạt chuẩn Tier-1.**
