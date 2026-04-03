# QTRADER — TIER-1 INSTITUTIONAL MASTER ASSESSMENT

> **Ngày rà soát**: 2026-04-03
> **Benchmark**: [standash-document.md](standash-document.md) (Tier-1 Institutional Master Specification)
> **Mục tiêu**: Đánh giá cực kỳ chi tiết đến từng file, từng dòng code về mức độ vi phạm kiến trúc, tiến độ hoàn thành, và lỗ hổng hệ thống. Đưa ra phương án tái sử dụng triệt để những khối kiến trúc đang bị bỏ hoang (Orphans).

---

## PHẦN 1: TỔNG QUAN HỆ THỐNG VÀ MA TRẬN RỦI RO (READINESS MATRIX)

QTrader hiện có `404` file Python, bao quát mọi Domain nghiệp vụ. Giá trị Engineering khổng lồ nhưng lại nằm ở trạng thái **Architecturally Unwired (Phân mảnh kiến trúc nghiêm trọng)**. Mức độ hoàn thiện tổng thể ước tính ~50-55%.

| Tiêu chí | Trạng thái | Điểm Yếu Chí Mạng Đi Kèm |
| :--- | :--- | :--- |
| **Zero Latency Protocol** | 🔴 FAILED (0/10) | Phát hiện `time.sleep()` ngang nhiên chặn luồng trong xử lý dữ liệu. Thiếu hoàn toàn tối ưu TCP (`TCP_NODELAY`). |
| **Pre-Trade Risk Gates** | 🔴 FAILED (2/10) | 3 Module Kill Switch chồng chéo. `WarModeEngine` đã xây xong 100% logic báo động nhưng bị **cô lập**, không được import vào bất kỳ luồng Execution nào. |
| **Stateful HA & Replication**| 🔴 FAILED (3/10) | Code `state_replication.py` đồng bộ Active/Passive cực chuẩn, nhưng Hàm `publish_state()` bị bỏ xó. Sẽ không có Failover <5s trên thực tế. |
| **Deterministic Isolation** | 🔴 FAILED (0/10) | Module `cpu_affinity.py` (Móc chặt Thread vào CPU Core) là "Ghost file" - không bao giờ được tải lên khi start hệ thống. |
| **Algorithmic SOR Execution** | 🔴 FAILED (1/10) | Toàn bộ Smart Order Router (SOR) và các thuật toán cắt lệnh (VWAP, TWAP) chỉ là cái vỏ. Các hàm bên trong toàn `return {}` hoặc `return []`. |
| **Error Handling Strictness** | 🔴 FAILED (2/10) | 174 lần gọi `except Exception:` nhưng không đưa lên hệ thống cảnh báo, gây hiện tượng văng lỗi ngầm (Silent Death). |

---

## PHẦN 2: "GHOST MODULES" VÀ ORPHANED FILES (MỔ XẺ VÀ CÁCH DÙNG HIỆU QUẢ)

Hệ thống có khoảng **80 file Python (chiếm gần 20%)** đóng vai trò là "Module Ma" (Orphans). Chúng chứa các thuật toán cực kỳ cao cấp, đạt chuẩn quỹ (Hedge-fund grade), nhưng chưa hề được "nối dây điện" vào Orchestrator.

Thay vì xóa bỏ mù quáng, dưới đây là phân tích chi tiết từng mảnh ghép và **Cách tích hợp hiệu quả nhất** để phát huy toàn bộ sức mạnh của chúng:

### 2.1 Cụm Phân Tích Lệnh Cấp Thấp (`execution/microstructure/` & `hft/`)

- **Danh sách file mồ côi**: `toxic_flow.py`, `hidden_liquidity.py`, `queue_model.py`, `hft/spoofing.py`.
- **Giá trị mang lại**: Phân tích sổ lệnh (Orderbook) siêu vi mô (microstructure) để nhận diện đội lái (spoofing), dòng tiền độc hại (toxic flow), và thanh khoản ngầm.
- **Cách dùng hiệu quả nhất**:
  - Không chạy độc lập. Hãy biến chúng thành các **Pre-Trade Filters** (Bộ lọc trước giao dịch) nằm bên trong `Standard Router`.
  - Lúc `route_order()` chuẩn bị nổ lệnh Limit: Gọi `toxic_flow.predict()`. Nếu xác suất bị "xả hàng" cao > 80%, Router sẽ tự động ép đổi sang Market Order hoặc huỷ lệnh tạm thời để tránh trượt giá bất lợi (Adverse Selection).

### 2.2 Cụm Quản Trị Khủng Hoảng và Phản Hồi (`feedback/` & `system/`)

- **Danh sách file mồ côi**: `feedback/incident_handler.py`, `feedback/dashboard.py`, `system/system_orchestrator.py`.
- **Giá trị mang lại**: Cơ chế tự động đối phó với sự cố và giám sát vòng lặp.
- **Cách dùng hiệu quả nhất**:
  - Tái cấu trúc 174 khối `except Exception:` đang rải rác. Khi xảy ra Exception rủi ro cao, không được im lặng hay in log suông, mà phải quăng sự kiện lên EventBus, nhắm đến đích là `incident_handler.py`.
  - Từ `incident_handler.py`, dựa theo thang độ rủi ro, module này trực tiếp kích hoạt lệnh gọi `WarModeEngine` để ngắt đòn bẩy toàn cục. Cấu trúc này tạo ra quy trình "Tự Chữa Lành" (Autonomic Healing).

### 2.3 Cụm Tự Động Tối Ưu, Sinh Học (Hệ `meta/`)

- **Danh sách file mồ côi**: Gần 13 file gồm `genetic.py`, `self_diagnostic.py`, `memory.py`, `governance_engine.py`, `shadow_enforcer.py`.
- **Giá trị mang lại**: Học máy tăng cường Meta-learning, thuật toán di truyền tự tìm trọng số (weight) Alpha tốt nhất mà không cần con người. Tuân thủ §8.1 Strategy Lifecycle.
- **Cách dùng hiệu quả nhất**:
  - Các module này quá nặng để nhét vào vòng lặp tốc độ cao (Core HFT/Execution).
  - Phải tách nguyên cụm `meta/` thành một **Off-path Background Process (Cronjob/Worker)**.
  - Hàng tuần/Hàng ngày, Process này sẽ rà soát DB/DuckDB log, chạy `genetic.py` để tìm tham số tối ưu mới, và push cấu hình xịn thông qua `Feature Flags` xuống thẳng Core Engine mà không cần Restart. `shadow_enforcer.py` sẽ lo việc theo dõi Paper-trade cho thuật toán mới đó.

### 2.4 Cụm Phân Tích Độ Trượt & Phí Tổn (`tca/`)

- **Danh sách file mồ côi**: 6 file (thiếu `__init__.py`) như `slippage.py`, `benchmark.py`, `implementation_shortfall.py`.
- **Giá trị mang lại**: Phân tích hụt PnL (Chi phí giao dịch Transaction Cost Analysis) sát ván.
- **Cách dùng hiệu quả nhất**:
  - Hiện tại Analytics đã có `tca_engine.py`. Phải gộp logic phân rã phí của cụm `tca/` (chất lượng rất tốt) thành thư viện nội bộ cho Analytics.
  - Ràng buộc **Feedback Loop**: Đo lường slippage từ `tca/` không được chỉ để "xem báo cáo offline". Dữ liệu độ trễ và Slippage của sàn Binance vs Coinbase phải được lưu vào Caching. Smart Order Router (`execution/router.py`) trước khi chẻ lệnh VWAP phải đọc rating từ `TCA` để điều hướng theo tỷ lệ (Sàn trượt ít thì chia nhiều lệnh).

### 2.5 Cụm Định Nghĩa Định Danh Kép (Order FSM Fragment)

- **Danh sách file mồ côi**: `execution/order_id.py` và `oms/replay_engine.py`.
- **Giá trị mang lại**: Cơ chế replay lại sổ lệnh và ID định danh kép chống trùng lệnh sàn.
- **Cách dùng hiệu quả nhất**:
  - `execution/order_id.py` cung cấp Global UUID có chống replay - cực kỳ hợp với chuẩn §4.7. Bắt buộc import vào tầng tạo `OrderEvent` để toàn bộ FSM theo vết ID này từ sinh ra lúc Signal cho tới Fill trên Sàn.
  - `replay_engine.py` là một máy du hành thời gian. Phục vụ đắc lực cho End-of-Day Audit. Phục dựng trạng thái. Cần chuyển hẳn về thư mục `audit/` để phòng Backoffice hoặc Data Science sử dụng độc lập.

### 2.6 Khủng Hoảng Duplicates (Logic trùng lặp tại Execution & Portfolio)

- **Danh sách file dư thừa**:
  - Execution adapter rác (`exchange/binance_adapter.py`, `adapters/binance_adapter.py`).
  - Portfolio allocator lộn xộn (`portfolio/` rỗng init, và đụng độ với `risk/portfolio/`).
- **Cách giải quyết**: Đây là "Lập trình viên viết ra, quên chưa xóa".
  - Chốt hạ 1 File 1 Chức năng.
  - Binance adapter chỉ chui vào `brokers/binance.py`.
  - Gom toàn bộ Capital Allocator về chuẩn `qtrader/portfolio/`. Loại bỏ các file copy bên trong `risk/portfolio/` để làm sạch thanh Namespace.

---

## PHẦN 3: VI PHẠM THIẾT KẾ CỐT LÕI (CORE RULE VIOLATIONS)

### 3.1 Chặn Luồng Bất Hợp Pháp (Blocking IO & Sleeps)

Theo luật §2.5 Standash: **Strictly No Sleep**. Các lỗi dưới đây đang bóp chết Event Loop:

- `data/market/coinbase_market.py`: Lệnh `time.sleep(0.15)` và `time.sleep(1.0)` nằm chờ rate limits cứng.
- `data/market/snapshot_recovery.py`: Chứa các lệnh sleep làm nghẽn quá trình tái tạo Orderbook.
- `execution/market_maker_live.py`: Logic market making bị block ngầm, làm tăng latency hàng order magnitude.
- `core/timer.py`: Lạm dụng vòng lặp kiểm tra thời gian.

### 3.2 Tối Ưu State Bị Nghẽn Bới Khối Lượng Dữ Liệu

Mặc dù đã có nỗ lực thêm các docstring `"""Fast copy without deepcopy."""`, hệ thống OMS/Execution ban đầu phụ thuộc vào `copy.deepcopy()` bên trong các khối `asyncio.Lock()`. Khi Portfolio tăng lên vài vạn vị thế, GC (Garbage Collection) của Python sẽ gây ra hiện tượng *Giật/Lag toàn cục > 100ms*, loại bỏ hoàn toàn khả năng giao dịch HFT. Cần 100% Memory Zero-copy (Immutable struct).

### 3.3 Thuật Toán "Chống Điếc" (Execution Stubs & Facades)

Logic cốt lõi của việc chuyển lệnh đang bị bỏ trống trắng trợn:

- **`execution/multi_exchange_adapter.py`**: Các method route nhiều sàn chỉ trả về `{}`.
- **`execution/routing/router.py`**: Hành động điều phối (Smart Order Route) trả ra `{}`. Không hề phân tích phí sàn nào rẻ hơn.
- **`execution/routing/fill_model.py` và `cost_model.py`**: Dự báo tỷ lệ chênh giá/khớp lệnh trống rỗng.
- **`execution/algos/vwap.py` & `twap.py`**: Thuật toán băm nhỏ lệnh cho các lệnh volume lớn trả ra mảng danh sách trống `[]`. Điều này khiến lệnh văng thẳng ra thị trường (trở thành DUMB Order thay vì SMART Order).

---

## PHẦN 4: SỰ PHÂN MẢNH KIẾN TRÚC VÀ RỦI RO HOẠT ĐỘNG (OPERATIONAL RISKS)

### 4.1 Rủi Ro Phân Quyền (Security & Governance)

- Tổ hợp an ninh lệnh **`security/order_signing.py`** chứa đầy đủ thuật toán để mã hoá ký xác nhận lệnh điện tử cho Audit. Nhưng file `execution_engine.py` (Lõi chốt đơn) không hề gắn lệnh gọi hàm `OrderSigning.sign()`. Mọi lệnh được đẩy lên Broker là **Unsigned (Lệnh trần)** - vi phạm Non-repudiation.
- Override hệ thống thủ công không được kích hoạt Event gắn vết, vi phạm luật kiểm toán.

### 4.2 Thảm Họa State Machine (Double FSM)

- Hệ thống bị tách ra với 2 Order FSM song song: Đầu tiên là `oms/order_fsm.py` chạy riêng để record. Thứ hai là luồng trong Execution Engine nội bộ chạy vòng đời.
- **Hệ quả**: Nếu một lệnh bị sàn báo REJECTED, có nguy cơ Orderbook thì giữ lệnh, nhưng OMS lại báo PENDING. Nguy cơ treo quỹ (Zombie Capital).

### 4.3 Giám Sát Và Thuyết Minh Lệnh Đặt (Explainability Missing)

- Mảng ML / Phân tích (như `phi2_controller.py`) tạo ra biểu đồ/lý do (reason / SHAP explanation) xác định tại sao AI mở vị thế.
- **Hệ quả**: Chỗ Log TradeExecution (`trade_logger.py`) và Analytics chối bỏ dữ liệu đó; Audit không thể thuyết minh cho Khách hàng lý do máy móc khớp lệnh.

---

## PHẦN 5: LỘ TRÌNH TÁI CẤU TRÚC VÀ TÍCH HỢP 4 BƯỚC KHẨN CẤP

> **Cảnh báo**: Bất kỳ bước nhảy vọt nào bổ sung Feature mới sẽ gây đổ vỡ hệ thống cục bộ. Lệnh dừng Update Logic mới để "Bắt Cầu Nối Điện" là bắt buộc.

### GIAI ĐOẠN 1: QUÉT SẠCH NỢ, SÁT NHẬP PACKAGES (CLEANUP)

- Thêm file rỗng `__init__.py` cho các thư mục quan trọng (`tca`, `portfolio`, `governance`) để khôi phục kiến trúc Package.
- Gộp cụm `tca/` vào `analytics/`.
- Xóa adapter trung lặp: `exchange/`, `adapters/`. Gom về `brokers/`.
- Gắn bẫy Lỗi (Fail-Fast): Đổi tất cả hàm trả `{}`/`[]` ở phần `Execution/Algos` thành `raise NotImplementedError("Missing Logic!")`. Tránh ảo tưởng code hoàn thiện.

### GIAI ĐOẠN 2: "BẮT CẦU" NỐI CÁC ORPHANS KHỦNG (SAFETY & WIRING)

- **Tích Hợp War Mode & Incident**: Đưa 174 block `except` vào gửi Event lên `incident_handler.py`. Module này sẽ nắm dây kéo cầu dao `WarModeEngine`. Nhúng hàm `WarModeEngine.check_order_allowed()` vào đầu hàm `execute_order(...)` của `ExecutionEngine`.
- **Gắn Mã Hoá Lệnh Đặt**: Yêu cầu gọi `OrderSigning.sign()` tại Adapter trước khi xả lệnh Websocket mua bán.

### GIAI ĐOẠN 3: ÁP ĐẶT ZERO LATENCY COMPLIANCE (THIẾT QUÂN LUẬT TỐC ĐỘ)

- Rút ruột toàn bộ hàm `time.sleep()`. Ép buộc dùng I/O async hoặc `asyncio.sleep()` ở Market Data layer (`coinbase_market.py`).
- Cấu hình Socket: Gắn cờ socket `TCP_NODELAY = 1` tại kết nối Binance/Coinbase Brokers.
- Hồi sinh `cpu_affinity.py`: Ép luồng event_loop Orchestrator chạy duy nhất trên Pin Core 0/1 bằng dòng lệnh đầu tiên khi start app.
- Kích hoạt Replication: Trong `StateStore.set_position()`, nổ hàm `StateReplicator.publish_state()` chép qua Server Backup.

### GIAI ĐOẠN 4: HỢP NHẤT Finite State Machine (FSM CONSOLIDATION)

- Hợp nhất 2 FSM: Chặt bỏ FSM tại `execution/order_fsm.py` — chỉ thao tác trên Source of Truth của `oms/order_fsm.py`.
- Dùng `order_id.py` từ vòng đời đầu tiên (Signal) để không bao giờ bị lệnh bị lệch track giữa OMS và Sàn.
- Bắt buộc vòng đời: `NEW` -> `ACK` -> `PARTIAL` -> `FILLED / CANCELLED / REJECTED`.

*(Mỗi thay đổi phải gắn kèm kết quả Test phủ sóng > 90% Code Coverage).*
