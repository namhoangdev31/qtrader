# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: PLATFORM SOVEREIGNTY (CORE)

**Vị trí**: `qtrader/core/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.26`  
**Mục tiêu**: Giải phẫu sâu toàn bộ **39 tệp** cấu thành hạ tầng nền tảng của QTrader — lớp cơ sở dưới cùng không thể sai lệch. Mọi tầng trên (Strategy, Risk, OMS) đều phụ thuộc vào tầng này cho tính xác định (Determinism), độ trễ (Latency) và an toàn dữ liệu (Data Integrity).

---

## KIẾN TRÚC 6 TRỤ CỘT (6-PILLAR SOVEREIGNTY)

```
Trụ 1 – HẠT NHÂN DI (DI KERNEL)     : container.py         → Singleton DI Registry (6 Core Authorities)
Trụ 2 – HỆ THẦN KINH (NERVOUS SYSTEM): event_bus.py, events.py, event_store.py, event_index.py
Trụ 3 – BỘ NHỚ TRUNG TÂM (MEMORY)   : state_store.py, state_replication.py
Trụ 4 – KIỂM SOÁT LUẬT (ENFORCEMENT) : enforcement_engine.py, fail_fast_engine.py, runtime_gatekeeper.py
Trụ 5 – SLA ĐỘ TRỄ (LATENCY SLA)    : latency_enforcer.py, backpressure_controller.py, cpu_affinity.py
Trụ 6 – ĐẦU MỐI GỐC (FOUNDATIONS)   : trace_authority.py, seed_manager.py, decimal_adapter.py, config.py, logger.py
```

---

## TRỤ 1: HẠT NHÂN DI — `container.py`

**Class chính**: `Container` (Singleton)

Điểm khởi đầu tuyệt đối của toàn hệ thống. Triển khai **Singleton DI Pattern** — chỉ có duy nhất một Container instance tồn tại trong cả vòng đời tiến trình.

* **6 Core Authorities đăng ký tại boot**:

| Tên Service | Loại | Vai trò |
|---|---|---|
| `config` | `ConfigManager` | Đọc và validate toàn bộ cấu hình YAML |
| `trace` | `TraceAuthority` | Sinh và lan truyền UUID trace_id xuyên suốt |
| `logger` | `qlogger` | Logger tập trung theo chuẩn loguru |
| `failfast` | `FailFastEngine` | Phản ứng xác định khi gặp lỗi |
| `decimal` | `math_authority` | Cổng phép tính tài chính không float |
| `seed` | `SeedManager` | Kiểm soát entropy cho tính xác định |

* **Fail Fast khi truy xuất sai**: `container.get("unknown")` → `KeyError` ngay tức thì — không im lặng.
* **`Container.reset()`**: Chỉ dành cho Unit Test — đặt lại Singleton về trạng thái chưa khởi tạo.

---

## TRỤ 2: HỆ THẦN KINH — EVENT INFRASTRUCTURE

### 1. FILE: `event_bus.py` (Hệ thống Dây Thần kinh)

**Class chính**: `EventBus`

Xe buýt sự kiện phân tán hỗ trợ **16 partition** song song, đảm bảo trật tự xử lý nghiêm ngặt theo từng Symbol/OrderID:

* **Phân vùng (Partitioning)**: Mỗi sự kiện được định tuyến tới 1 trong 16 `asyncio.Queue(maxsize=20000)` dựa trên `partition_key`. Cùng symbol → cùng partition → không bao giờ xử lý đảo thứ tự.
* **Backpressure Gate**: Trước mỗi `publish()`, kiểm tra `should_drop()` — nếu Queue đang căng, các sự kiện ưu tiên thấp (Heartbeat) bị loại bỏ trước.
* **Immutable Event Copy**: Khi `partition_key` chưa có, dùng `event.model_copy(update={...})` thay vì mutate trực tiếp — giữ đúng ngữ nghĩa bất biến của Pydantic model.
* **Safe Delivery với Retry**: `_safe_deliver()` bọc mỗi handler trong `asyncio.wait_for(timeout=5s)`. Thất bại → retry tối đa 3 lần mà không block các sự kiện khác trong partition.
* **Post-Delivery Persist**: `_partition_worker` chỉ ghi vào `EventStore` **sau khi** deliver thành công — đảm bảo không ghi phantom event chưa được xử lý.

---

### 2. FILE: `event_store.py` + `event_index.py` (Hệ thống Lưu trữ Pháp lý)

Log bất biến mọi sự kiện dạng JSONL với `fsync()` — toàn vẹn vật lý đĩa đảm bảo dữ liệu không mất dù mất điện đột ngột. `EventIndex` theo dõi các `event_id` đã xử lý, chặn tuyệt đối redelivery trùng lặp (Idempotency Guard).

---

## TRỤ 3: BỘ NHỚ TRUNG TÂM — STATE MANAGEMENT

### 3. FILE: `state_store.py` (Kho Trạng thái Duy nhất - SSOT)

**Class chính**: `StateStore` | **Data Classes**: `Position`, `Order`, `RiskState`, `SystemState`

Triển khai Memory-Safe State với **4 kỷ luật cứng**:

* **Copy-on-Write**: Mọi `get_*()` đều gọi `.copy()` trên từng object trước khi trả ra ngoài lock → caller không bao giờ nhận được reference vào internal state.
* **Giới hạn Bộ nhớ Tuyệt đối**:
  - Equity Curve: `deque(maxlen=100,000)` — tự động loại điểm cũ nhất khi đầy.
  - Active Orders Cap: 10,000 lệnh — từ chối thêm lệnh mới nếu vượt ngưỡng.
  - Positions Cap: 5,000 vị thế.
* **Monotonic Version Counter**: Mỗi lần `set_*()` tăng `state.version += 1` — dùng để phát hiện xung đột khi đồng bộ.
* **Tích hợp Replication**: Mỗi thay đổi state tự động gọi `_publish_if_primary()` — nếu node đang là `PRIMARY` thì đẩy snapshot sang Standby.

---

### 4. FILE: `state_replication.py` (Đồng bộ Active/Passive – Standash §5.2)

**Class chính**: `StateReplicator`

Giao thức HA (High Availability) với **Failover < 5 giây**:

* **Checksum SHA-256**: Trước khi Primary publish, serialize state thành JSON (sorted keys), tính `SHA-256[:16]`. Standby nhận → tính lại → so sánh. Không khớp → từ chối áp dụng, log lỗi `CHECKSUM_MISMATCH`.
* **Heartbeat Monitor**: Standby theo dõi `time_since_last_heartbeat`. Nếu > `failover_threshold_s = 5.0` giây → gọi `execute_failover()` tự nâng cấp thành PRIMARY.
* **Chống Failover Vòng lặp**: Sau mỗi lần failover, reset `_last_peer_heartbeat = now()` để không kích hoạt lại ngay lập tức.
* **Replication Log bất biến**: Mọi hành động `PUBLISH`, `RECEIVE`, `FAILOVER` đều được append-only vào `_replication_log` để kiểm toán sau.

---

## TRỤ 4: KIỂM SOÁT LUẬT — ENFORCEMENT

### 5. FILE: `enforcement_engine.py` (Cổng Thực thi Chủ quyền)

**Class chính**: `EnforcementEngine` | **Decorator**: `@guard`

Cảnh sát nội bộ kiểm tra **2 ràng buộc tại mỗi lần thực thi**:

* **C3 – Trace Propagation**: Mỗi `context` và `event` phải có `trace_id`. Không có → `_handle_violation("C3", ...)` → `ViolationHandler` quyết định BLOCK/ALERT/HALT.
* **C4 – Numeric Precision**: Quét các field tài chính (`price`, `quantity`, `close`...). Nếu phát hiện `isinstance(val, float)` → vi phạm C4 — tất cả tính toán tiền tệ phải là `Decimal`.
* **`@guard` Decorator**: Tự phát hiện async/sync. Sync → raise `RuntimeError` ngay ("Synchronous execution not supported under EnforcementEngine") — ép buộc toàn hệ thống thuần async.

---

### 6. FILE: `fail_fast_engine.py` (Engine Phản ứng Xác định)

**Class chính**: `FailFastEngine`

Phân loại lỗi và áp phản ứng **3 cấp độ**:

| Severity | Loại lỗi | Hành động |
|---|---|---|
| ≥ 3 (Critical) | Lỗi hạ tầng, DB, Kill Switch | `_halt_system()` → `GlobalKillSwitch` → nếu không có Orchestrator → `sys.exit(1)` |
| 2 (Warning) | Lỗi chiến lược | `_isolate_module()` → cô lập component |
| 1 (Info) | Lỗi thoáng qua | `_trigger_retry()` → theo dõi escalation |

* **Escalation Logic**: `RecoverableError` xuất hiện > `max_retries = 3` lần trong cửa sổ `escalation_window = 60s` → tự động leo thang thành `CriticalError`.

---

## TRỤ 5: SLA ĐỘ TRỄ — LATENCY ENFORCEMENT

### 7. FILE: `latency_enforcer.py` (Kiểm soát SLA 100ms – Standash §5.1)

**Class chính**: `LatencyEnforcer` | **Context Manager**: `with enforcer.measure_stage("alpha_computation")`

Ngân sách độ trễ tuyệt đối cho từng bước trong pipeline:

| Stage | Budget |
|---|---|
| `market_data_ingestion` | 5ms |
| `alpha_computation` | 5ms |
| `signal_generation` | 5ms |
| `portfolio_allocation` | 10ms |
| `risk_check` | 5ms |
| `order_routing` | 10ms |
| `order_submission` | 10ms |
| `fill_processing` | 50ms |
| **Tổng `total_end_to_end`** | **100ms** |

* **Đo bằng `time.perf_counter_ns()`**: Nanosecond precision — không bị ảnh hưởng bởi system clock drift.
* **Warning ngưỡng 80%**: Khi stage đạt 80% budget → cảnh báo, chưa vi phạm. Giúp phát hiện xu hướng trước khi breach thật sự.
* **`fail_on_breach = True`**: Vi phạm budget → raise `LatencyViolation` ngay, ngăn pipeline tiếp tục với data stale.
* **Circular Report Buffer**: Lưu tối đa 1000 báo cáo pipeline, tự trim về 500 khi đầy.

---

## TRỤ 6: ĐẦU MỐI GỐC — FOUNDATION AUTHORITIES

### 8. FILE: `trace_authority.py` (Chủ quyền Truy vết)

**Class chính**: `TraceAuthority` (Static Methods)

Dùng `contextvars.ContextVar[UUID]` để lan truyền `trace_id` xuyên suốt chuỗi `await` bất đồng bộ mà không cần truyền tham số tường minh — mỗi coroutine kế thừa `trace_id` của coroutine cha tự động.

* **`ensure_trace()`**: Nếu không có trace đang hoạt động → tự sinh UUID mới + log warning. Hệ thống không bao giờ có event vô danh.
* **`wrap_with_trace(trace_id)`**: Context Manager chuẩn `__enter__/__exit__` dùng `ContextVar.reset(token)` để khôi phục trace cũ sau khi khối code hoàn thành — không làm hỏng trace của caller.
* **`propagate(source_event)`**: Trích `trace_id` từ event (ưu tiên field `.trace_id`, fallback sang `.metadata["trace_id"]`) và inject vào context hiện tại.

---

**SƠ ĐỒ LUỒNG KHỞI ĐỘNG (BOOT SEQUENCE)**

```
Container.__init__()
    → ConfigManager (YAML load + Pydantic validate)
    → SeedManager (global entropy fix)
    → TraceAuthority (ContextVar ready)
    → FailFastEngine (error taxonomy map)
    → math_authority (Decimal precision rules)
    → qlogger (loguru sink config)
          ↓
EventBus.start()  → 16 Partition Workers (asyncio.Task pool)
StateStore.__init__() → deque(maxlen=100k) + asyncio.Lock
LatencyEnforcer (global singleton, budget map locked)
EnforcementEngine (C3/C4 guards armed)
```

---

**KẾT LUẬN AUDIT**: `qtrader/core` là lớp "Hiến pháp" của toàn hệ thống — mọi module khác chỉ được phép hoạt động trong khuôn khổ do Core quy định. 6 trụ cột phân ly trách nhiệm tuyệt đối: DI Kernel không biết về EventBus, EventBus không biết về StateStore, tất cả đều kết nối qua Container. Mô hình này đảm bảo **Kiểm thử độc lập từng trụ** và **Nâng cấp không ảnh hưởng chéo**.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Core Platform Sovereignty Deep Audit — Verified)`
