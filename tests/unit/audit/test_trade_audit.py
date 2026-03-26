import asyncio
import uuid
from decimal import Decimal
import pytest
from qtrader.core.events import (
    SignalEvent, SignalPayload, 
    OrderEvent, OrderPayload, 
    RiskApprovedEvent, RiskApprovedPayload, 
    RiskRejectedEvent, RiskRejectedPayload,
    FillEvent, FillPayload,
    EventType
)
from qtrader.audit.audit_store import AuditStore
from qtrader.audit.trade_audit import TradeLifecycleEngine


@pytest.mark.asyncio
async def test_complete_trade_lifecycle_reconstruction():
    """Verify that a Signal -> Order -> Risk -> Fill sequence is correctly reconstructed."""
    store = AuditStore(":memory:")
    engine = TradeLifecycleEngine(store)
    trace_id = uuid.uuid4()
    
    # 1. T=0: Signal (BTC - Buy)
    await store.append(SignalEvent(
        trace_id=trace_id, source="Alpha_X", timestamp=1000000,
        payload=SignalPayload(symbol="BTC/USD", signal_type="BUY", strength=1.0)
    ))
    
    # 2. T=100ms: Order Created ($50,000)
    await store.append(OrderEvent(
        trace_id=trace_id, source="Strategy_A", timestamp=1100000,
        payload=OrderPayload(order_id="ORD_RECON_01", symbol="BTC/USD", action="BUY", quantity=2.0, price=50000.0)
    ))
    
    # 3. T=150ms: Risk Approved
    await store.append(RiskApprovedEvent(
        trace_id=trace_id, source="RiskEngine", timestamp=1150000,
        payload=RiskApprovedPayload(order_id="ORD_RECON_01")
    ))
    
    # 4. T=1000ms: Filled at $50,100 (Slippage: $100 worse)
    await store.append(FillEvent(
        trace_id=trace_id, source="Binance", timestamp=2000000,
        payload=FillPayload(order_id="ORD_RECON_01", symbol="BTC/USD", side="BUY", quantity=2.0, price=50100.0)
    ))
    
    # Reconstruct the lifecycle
    record = engine.reconstruct(trace_id)
    
    # Verifications
    assert record.status == "COMPLETED"
    assert record.symbol == "BTC/USD"
    # Latency: (2000000 - 1000000) / 1000 = 1000ms (1 second)
    assert record.execution_latency_ms == 1000.0
    # Slippage: (50100 - 50000) / 50000 * 10000 = 20 basis points
    assert record.slippage_bps == 20.0


@pytest.mark.asyncio
async def test_risk_rejected_lifecycle_reconstruction():
    """Verify that a trade rejected by the Risk Engine is correctly identified and flagged."""
    store = AuditStore(":memory:")
    engine = TradeLifecycleEngine(store)
    trace_id = uuid.uuid4()
    
    # 1. Order Created
    await store.append(OrderEvent(
        trace_id=trace_id, source="Strategy_B", timestamp=5000000,
        payload=OrderPayload(order_id="ORD_RECON_02", symbol="ETH/USD", action="SELL", quantity=100, price=3000.0)
    ))
    
    # 2. Risk Rejected
    await store.append(RiskRejectedEvent(
        trace_id=trace_id, source="RiskEngine", timestamp=5005000,
        payload=RiskRejectedPayload(order_id="ORD_RECON_02", reason="MAX_EXPOSURE_VIOLATION", metric_value=1.8, threshold=1.5)
    ))
    
    # Reconstruct the lifecycle
    record = engine.reconstruct(trace_id)
    
    assert record.status == "REJECTED"
    assert record.rejection_reason == "MAX_EXPOSURE_VIOLATION"
    assert record.fill_time is None
    assert record.pnl == 0.0


@pytest.mark.asyncio
async def test_incomplete_trade_lifecycle_detection():
    """Verify that trades missing critical FILL events are correctly marked as INCOMPLETE."""
    store = AuditStore(":memory:")
    engine = TradeLifecycleEngine(store)
    trace_id = uuid.uuid4()
    
    # 1. Signal & Order Only
    await store.append(SignalEvent(trace_id=trace_id, source="Alpha", payload=SignalPayload(symbol="SOL/USD", signal_type="BUY", strength=0.5)))
    await store.append(OrderEvent(trace_id=trace_id, source="Strat", payload=OrderPayload(order_id="ORD_RECON_03", symbol="SOL/USD", action="BUY", quantity=10)))
    
    record = engine.reconstruct(trace_id)
    
    assert record.status == "INCOMPLETE"
    assert record.symbol == "SOL/USD"
    assert record.fill_time is None
