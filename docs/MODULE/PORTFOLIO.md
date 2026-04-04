# ĐIỀU TRA KIẾN TRÚC NỘI BỘ: KẾ TOÁN QUỸ & DANH MỤC ĐẦU TƯ (PORTFOLIO)

**Vị trí**: `qtrader/portfolio/`  
**Cố vấn Kỹ thuật**: `Antigravity Institutional Audit Ver 4.25`  
**Yêu cầu**: Phân tích giải phẫu sâu nội bộ nguyên khối (File-by-File Deep Audit) đối với tất cả lớp lang quản lý vốn và kế toán quỹ của nền tảng.

---

## 1. KHỐI KẾ TOÁN KÉP (DOUBLE-ENTRY ACCOUNTING)

Đây là tầng lõi thấp nhất, đảm bảo tính vẹn toàn tuyệt đối của dòng mạch tài chính, không cho phép tiền tự nhiên "sinh ra" hoặc "biến mất".

### `ledger_entry_model.py` (Mô hình Dữ liệu Sổ cái)

Bọc giao dịch bằng DataClass `TransactionRecord`.

- **Ràng buộc Toán học**: Bất kỳ sự chênh lệch nào giữa Tổng Ghi Nợ (Debit) và Tổng Ghi Có (Credit) đều sập bẫy trong hàm `validate_balance()`. Ngưỡng sai số Epsilon được ép tại `1e-10`.

### `cash_ledger.py` (Sổ cái Tiền mặt)

Lớp `CashLedger` là thủ quỹ của nền tảng.

- **Bất biến (Immutability)**: Toàn bộ giao dịch sau khi thỏa mãn phương trình `Σ Debit - Σ Credit = 0` sẽ bị phân rã thành các `LedgerEntryEvent` và lưu cứng vào EventStore (partition theo `account_id`).
- **Tuyệt đối Không lưu Biểu hiện Memory**: Không có biến số dư. `get_balance()` tính số dư bằng cách lật lại file Log và thiết nghịch đảo nợ/có bằng class `Decimal` của Python.

### `funding_engine.py` (Động cơ Tính phí Qua đêm)

QTrader giao dịch phái sinh (Perpetual Futures), do đó phí Funding xảy ra mỗi 8h.

- **Tính toán**: $Amount = Quantity \times MarkPrice \times FundingRate$.
- **Ánh xạ Kế toán Kép**: Hàm `create_ledger_transaction` ngay lập tức sinh ra một bút toán Nợ/Có. Nếu User trả phí (Paying) $\rightarrow$ Giảm Cash User, Tăng vào Pool Hệ thống (System Funding Pool).

### `fee_tracker.py` (Động cơ Gom Phí)

Hoạt động như một máy chụp X-quang Snapshot. Chia quỹ đạo cắt máu thành các cột Maker, Taker, Funding, Withdrawal. Hàm `record_trade_fee` không lưu vào Sổ cái mà phục vụ cho Báo cáo Chạy nhanh (Telemetry).

### `nav_engine.py` (Hành vi Chốt sổ Mark-to-Market)

- Điểm quyết toán ròng giá trị thật: $NAV = Cash\_Ledger + \Sigma (Quantity \times MarkPrice) - CumulativeFees$.
- Tách bạch Unrealized PnL và Realized PnL cho từng vòng tuần hoàn thay vì cọng dồn bừa bãi.

---

## 2. KHỐI ĐIỀU PHỐI & PHÂN BỔ TRẢI THẢM (ALLOCATION & SIZING)

Tầng quản lý "Cách tiêu tiền" sinh lời. Tương tác với tín hiệu và hệ phi tuyến thị trường.

### `allocator.py` (Động cơ Cấp phát Vốn Phân tán)

* `CapitalAllocationEngine`: Là bộ tư lệnh Rủi ro Ngang giá (Risk Parity). Nếu thuật toán trả vế 5 tín hiệu Bot có điểm Sharpe, hệ thống sẽ:
    1. Chặn `max_cap = 0.20`: Bất kể Bot đó xuất sắc đến đâu, cao nhất chỉ dc châm 20% vốn tổng.
    2. Nếu trọng số quá 20% $\rightarrow$ Thu hồi phần dôi dư (Excess) nhồi phễu đệ quy thả xuống các hệ thống dưới (Trickle Down Redistribute).
- `CapitalAllocator`: Lớp Legacy tính trọng số $w$ theo ma trận $Sharpe \times InverseVolatility \times CorrelationPenalty$.

### `position_sizing.py` (Van điều áp Quy mô Lệnh)

Tập hợp tinh hoa các mô hình Định lượng Rủi ro (Quant Sizing):

1. **`RiskAdaptivePositionSizer` (Inverse Volatility)**: $Size_{new} = BaseSize \times \frac{TargetVol}{\sigma_{current}}$. Bão bùng thì giảm lệnh, Biển lặng thì bung volume.
2. **`ATRPositionSizer`**: Vào lệnh tĩnh theo ngân sách cược / ATR.
3. **`PositionSizer` (Kelly Criterion)**: Ép sát định lý xác suất Kelly $f = \frac{p(b+1) - 1}{b}$ kết hợp hệ số chặn `f_max` chống cháy xích mâm.

---

## 3. KHỐI KIỂM SOÁT BẢO VỆ CHÍNH (RISK & LOCKOUT LIMITS)

Trạm gác cổng chống cháy quỹ (Fund Blowup).

### `capital_flow.py` (Canh gác Dòng Vốn Tự có)

* Quản lý hàm Nạp/Rút của nhà đầu tư. Tuân thủ định lý tĩnh:
  - Nếu hệ thống đang ôm vị thế rủi ro (Open Exposure). Lệnh xin Rút Tiền ném về bẫy `DENIED_OPEN_EXPOSURE` ngay lập tức để né sụp đổ hụt chân Margin.

### `drawdown_controller.py` (Luật Kìm hãm Sụt đỉnh)

Luật 3 Nấc Bất Tử dựa trên Đỉnh Cao Nhất Lịch Sử (Peak Equity):

- Trượt 5% từ đỉnh $\rightarrow$ Cắt 25% khối lượng đánh của mọi Bot.
- Trượt 10% từ đỉnh $\rightarrow$ Giảm 50%.
- Trượt 15% $\rightarrow$ Cắt Cầu Dao (`stop_level`), ép Lockout toàn cục (Hệ số `Multiplier = 0.0`). Cấm giao dịch bảo toàn vốn gốc.

### `risk_monitor.py` (Bàn Điều khiển Thời gian thực)

Phễu hợp nhất (Aggregated Risk) của toàn thể hệ thống đong đếm qua phương trình:
$$Risk_{Live} = (30\% \times VaR) + (50\% \times Drawdown) + (20\% \times Exposure)$$
Nếu chọc vỡ hạn mức `risk_limit = 1.0`, báo động `CRITICAL` nổ thẳng lên Telemetry.

---

**KẾT LUẬN AUDIT**: `qtrader/portfolio` cấu thành từ 10 phân tử nhưng chia thành 3 lớp phân cấp quyền lực sắc bén: **Bảo vệ gốc (Ledger Kép) $\rightarrow$ Cấp vốn đầu tư (Allocator/Sizing) $\rightarrow$ Cầu dao khẩn (Risk/Drawdown)**. Mọi thứ được khóa chặt hoàn hảo bởi Toán học định lượng phi trạng thái (State-less math).

**KÝ XÁC NHẬN**: `Antigravity AI Agent (Institutional Portfolio File-by-File Deep Audit - Verified Secure)`
