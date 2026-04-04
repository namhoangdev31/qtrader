# AUDIT CHI TIẾT MODULE: EXECUTION (INSTITUTIONAL ORDER LIFECYCLE)

**Vị trí**: `qtrader/execution/`
**Mục tiêu**: Vận hành "Last Mile" của hệ thống giao dịch với kỷ lục độ trễ cực thấp (Zero Latency), tối ưu hóa vị thế qua Smart Order Routing (SOR) và bảo vệ vốn bằng hệ rào chắn Pre-Trade định chế.

---

## 1. BỘ MÁY THỰC THI ĐỊNH CHẾ (EXECUTION CORE)

### 1.1 `execution_engine.py`: Stateless & Latency-Enforced

QTrader áp dụng triết lý Stateless Execution để đảm bảo khả năng phục hồi (Resiliency) tuyệt đối.

- **`execute_order()`**: Được bảo vệ bởi `@enforce_latency(threshold_ms=50.0)` và `@guard`.
- **War Mode (Standash §6.4)**: Chốt chặn rủi ro thị trường cực đoan. Thực thi các quy tắc `allow_hedging`, `allow_unwind` và `max_exposure_pct`.
- **Event-Driven Retries**: Loại bỏ `while/sleep` polling, sử dụng `RetryOrderEvent` cho các nỗ lực tái đặt lệnh sau lỗi.

### 1.2 `reconciliation_engine.py`: Đối soát Thời gian thực

Hệ thống audit nội bộ liên tục để đảm bảo tính nhất quán (Consistency).

- **Mandatory Audit (Standash §4.9)**: Sau mỗi `FillEvent`, thực hiện đối soát: `Diff = OMS_Pos - Exchange_Pos`.
- **`Diff != 0` → `TRADING_HALT`**: Tự động kích hoạt Kill Switch nếu phát hiện sai lệch trạng thái.

### 1.3 `trade_logger.py` & `order_id.py`: Truy vết Pháp y

- **Institutional Format**: Lưu vết giao dịch theo chuẩn `[ts][trace_id][symbol][side][qty][price]`.
- **Idempotency**: `OrderIDGenerator` sử dụng UUID4 kết hợp nanosecond timestamp để ngăn chặn đặt lệnh trùng lặp.

---

## 2. ĐIỀU PHỐI LỆNH THÔNG MINH (SOR)

### 2.1 `smart_router.py` & `routing/router.py`

Hệ thống phân phối lệnh đa sàn tự động tối ưu hóa điểm khớp (Execution Price).

- **Dynamic Scoring Matrix**: Điểm số Venue (`S_v`) được tính theo công thức: `S_v = (P_fill,v * L_v) / C_v`.
- **Sub-Models**:
  - **`liquidity_model.py`**: Đánh giá độ sâu đa tầng (Multi-level Depth).
  - **`cost_model.py`**: Ước tính Spread + Fees + Slippage.
  - **`fill_model.py`**: Dự báo xác suất khớp dựa trên độ trễ Round-trip.

---

## 3. VI CẤU TRÚC THỊ TRƯỜNG (MICROSTRUCTURE AI)

### 3.1 `microstructure/toxic_flow.py`: Dự báo Toxicity (τ)

- **Adverse Selection Protection**: Phát hiện Informed Trading (Dòng tiền độc hại). Nếu `τ → 1.0`, hệ thống sẽ hạ mức ưu tiên hoặc tạm dừng đặt lệnh Limit để tránh bị chọn lọc ngược.

### 3.2 `microstructure/microprice.py` & `imbalance.py`

- **Fair Value (Microprice)**: Tính toán giá trị thực của tài sản dựa trên sự mất cân bằng giữa Bid và Ask (Orderbook Imbalance).
- **`queue_model.py`**: Ước tính vị trí của lệnh trong hàng đợi vật lý của sàn.

---

## 4. THUẬT TOÁN GIAO DỊCH (EXECUTION ALGOS)

### 4.1 `algos/`: Benchmark Algos

Triển khai các thuật toán tiêu chuẩn định chế để giảm thiểu Market Impact:

- **VWAP / TWAP**: Phân phối lệnh theo khối lượng hoặc thời gian.
- **POV (Percentage of Volume)**: Thực thi lệnh song hành với nhịp điệu thanh khoản của thị trường.

### 4.2 `market_maker.py`: Inventory Management

- **Alpha-driven Spreads**: Tự động điều chỉnh Spread Bid-Ask dựa trên biến động và mức tồn kho (Inventory Risk Management).

---

## 5. RÀO CHẮN RỦI RO PRE-TRADE (SAFETY GATES)

### 5.1 `pre_trade_risk.py`: Hard-Gate Protection

Chốt chặn cuối cùng trước khi lệnh rời khỏi hệ thống (Standash §4.6).

- **Fat-finger**: Chặn Price/Qty deviation cực đoan.
- **Concentration**: Giới hạn tỉ trọng tối đa 5% danh mục cho mỗi mã.
- **Rate-Limiting**: Kiểm soát tần suất gửi lệnh (Orders per Second) để tránh API Ban.

---

## 6. MÔ PHỎNG & SHADOW (THE SANDBOX)

### 6.1 `shadow_engine.py`: Live-Parallel Sandbox (Standash §4.11)

- **Live GAP Analysis**: Chạy giả lập song song với lệnh thật để đo lường độ lệch (Execution Gap). Nếu GAP > 20%, hệ thống tự động kích hoạt Emergency Halt.
- **`orderbook_simulator.py`**: Giả lập sổ lệnh L3 với market impact và latency modeling.

---

**KẾT LUẬN AUDIT**: Module Execution của QTrader đạt tiêu chuẩn **Institutional Execution Rigor**. Mọi pha của vòng đời lệnh đều được giám sát, đối soát và bảo vệ bởi các rào chắn rủi ro đa tầng.

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Execution Audit Ver 4.14 - Final)`
