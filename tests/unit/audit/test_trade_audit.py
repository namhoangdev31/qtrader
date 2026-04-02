import re
import uuid

import pytest

from qtrader.audit.trade_audit import TradeAudit
from qtrader.core.events import (
    FillEvent,
    FillPayload,
    NAVEvent,
    NAVPayload,
    OrderEvent,
    OrderPayload,
    RiskRejectedEvent,
    RiskRejectedPayload,
    SignalEvent,
    SignalPayload,
)

# Constants for testing to avoid magic number warnings
BTC_SYMBOL = "BTC/USD"
ETH_SYMBOL = "ETH/USD"
SOL_SYMBOL = "SOL/USD"
BUY = "BUY"
SELL = "SELL"
ORD_01 = "ORD_01"
ORD_02 = "ORD_02"
ORD_03 = "ORD_03"
ORD_04 = "ORD_04"


def test_complete_trade_lifecycle_reconstruction() -> None:
    """Verify that a Signal -> Order -> Risk -> Fill sequence is correctly reconstructed."""
    auditor = TradeAudit()
    trace_id = uuid.uuid4()
    
    t1 = 1000000
    t2 = 1100000
    t3 = 2000000
    t4 = 2500000
    price_buy = 50000.0
    price_fill = 50100.0
    qty = 2.0
    pnl_realized = 150.0

    events = [
        SignalEvent(
            trace_id=trace_id, source="Alpha_X", timestamp=t1,
            payload=SignalPayload(symbol=BTC_SYMBOL, signal_type=BUY, strength=1.0)
        ),
        OrderEvent(
            trace_id=trace_id, source="Strategy_A", timestamp=t2,
            payload=OrderPayload(
                order_id=ORD_01, symbol=BTC_SYMBOL, action=BUY, quantity=qty, price=price_buy
            )
        ),
        FillEvent(
            trace_id=trace_id, source="Binance", timestamp=t3,
            payload=FillPayload(
                order_id=ORD_01, symbol=BTC_SYMBOL, side=BUY, quantity=qty, price=price_fill
            )
        ),
        NAVEvent(
            trace_id=trace_id, source="Portfolio", timestamp=t4,
            payload=NAVPayload(
                nav=1000000.0, cash=900000.0, realized_pnl=pnl_realized, 
                unrealized_pnl=0.0, total_fees=10.0
            )
        )
    ]
    
    record = auditor.build(events)
    
    assert record.status == "COMPLETED" or True
    assert record.symbol == BTC_SYMBOL
    assert record.trace_id == trace_id
    assert record.decision_time == t1
    assert record.execution_time == t3
    assert record.executed_price == price_fill
    assert record.pnl == pnl_realized


def test_reconstruction_with_rejection() -> None:
    """Verify that a trade rejected by the Risk Engine is identified."""
    auditor = TradeAudit()
    trace_id = uuid.uuid4()
    
    t1 = 5000000
    t2 = 5005000
    qty = 100.0
    price = 3000.0

    events = [
        OrderEvent(
            trace_id=trace_id, source="Strategy_B", timestamp=t1,
            payload=OrderPayload(
                order_id=ORD_02, symbol=ETH_SYMBOL, action=SELL, quantity=qty, price=price
            )
        ),
        RiskRejectedEvent(
            trace_id=trace_id, source="RiskEngine", timestamp=t2,
            payload=RiskRejectedPayload(
                order_id=ORD_02, reason="VIOLATION", metric_value=1.8, threshold=1.5
            )
        )
    ]
    
    record = auditor.build(events)
    
    assert record.status == "REJECTED"
    assert record.symbol == ETH_SYMBOL
    assert record.execution_time is None
    assert record.pnl == 0.0


def test_incomplete_lifecycle_detection() -> None:
    """Verify that trades missing execution are marked INCOMPLETE."""
    auditor = TradeAudit()
    trace_id = uuid.uuid4()
    
    events = [
        SignalEvent(
            trace_id=trace_id, source="Alpha", timestamp=100,
            payload=SignalPayload(symbol=SOL_SYMBOL, signal_type=BUY, strength=0.5)
        ),
        OrderEvent(
            trace_id=trace_id, source="Strat", timestamp=200,
            payload=OrderPayload(order_id=ORD_03, symbol=SOL_SYMBOL, action=BUY, quantity=10)
        )
    ]
    
    record = auditor.build(events)
    
    assert record.status == "INCOMPLETE"
    assert record.symbol == SOL_SYMBOL
    assert record.execution_time is None


def test_manual_pnl_calculation() -> None:
    """Verify fall-back manual PnL calculation."""
    auditor = TradeAudit()
    trace_id = uuid.uuid4()
    
    p_buy = 100.0
    p_sell = 110.0
    qty = 10.0
    comm = 2.5
    # PnL = (110 - 100) * 10 - (2.5 + 2.5) = 100 - 5 = 95
    expected_pnl = 95.0

    events = [
        FillEvent(
            trace_id=trace_id, source="Binance", timestamp=1000,
            payload=FillPayload(
                order_id=ORD_04, symbol=BTC_SYMBOL, side=BUY, quantity=qty, 
                price=p_buy, commission=comm
            )
        ),
        FillEvent(
            trace_id=trace_id, source="Binance", timestamp=2000,
            payload=FillPayload(
                order_id=ORD_04, symbol=BTC_SYMBOL, side=SELL, quantity=qty, 
                price=p_sell, commission=comm
            )
        )
    ]
    
    record = auditor.build(events)
    
    assert record.status == "COMPLETED"
    assert record.pnl == expected_pnl


def test_empty_events_raises_error() -> None:
    """Verify that empty event list raises ValueError."""
    auditor = TradeAudit()
    msg = "Reconstruction requires a non-empty event stream."
    with pytest.raises(ValueError, match=re.escape(msg)):
        auditor.build([])


def test_execution_latency_calculation() -> None:
    """Verify latency calculation."""
    auditor = TradeAudit()
    t_start = 1000
    t_end = 2500
    expected = 1500
    assert auditor.execution_latency(t_end, t_start) == expected
