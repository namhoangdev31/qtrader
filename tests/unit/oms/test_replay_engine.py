import asyncio
import os
import shutil
import uuid
from decimal import Decimal

import pytest

from qtrader.core.event_store import FileEventStore
from qtrader.core.events import (
    EventType,
    FillEvent,
    FillPayload,
    MarketEvent,
    MarketPayload,
    OrderEvent,
    OrderPayload,
)
from qtrader.oms.replay_engine import ReplayEngine, ReplayError


@pytest.fixture
def event_store():
    """Create a temporary event store for replaying events."""
    test_path = "tmp/test_replay_store"
    if os.path.exists(test_path):
        shutil.shutil.rmtree(test_path) if hasattr(shutil, "shutil") else shutil.rmtree(test_path)
    
    os.makedirs(test_path)
    store = FileEventStore(base_path=test_path)
    yield store
    
    # Cleanup after test
    if os.path.exists(test_path):
        shutil.rmtree(test_path)


@pytest.mark.asyncio
async def test_reproducible_state_reconstruction(event_store):
    """Verify that multiple replay runs on the same events produce identical state hashes."""
    engine = ReplayEngine(event_store)
    symbol = "BTC/USDT"
    trace_id = uuid.uuid4()
    
    # --- Sequence of events ---
    # 1. Send Order
    order_id = "TEST_REPLAY_001"
    evt_order = OrderEvent(
        trace_id=trace_id, 
        source="Strategy",
        payload=OrderPayload(order_id=order_id, symbol=symbol, action="BUY", quantity=1.0, price=50000.0),
        partition_key=symbol
    )
    await event_store.append(evt_order)
    
    # 2. Receive Partial Fill
    evt_fill1 = FillEvent(
        trace_id=trace_id, 
        source="Exchange",
        payload=FillPayload(order_id=order_id, symbol=symbol, side="BUY", quantity=0.5, price=50000.0),
        partition_key=symbol
    )
    await event_store.append(evt_fill1)
    
    # 3. Market Update
    evt_market = MarketEvent(
        trace_id=trace_id, 
        source="Feed",
        payload=MarketPayload(symbol=symbol, bid=51000.0, ask=51100.0),
        partition_key=symbol
    )
    await event_store.append(evt_market)
    
    # Run Replay multiple times
    h1 = ReplayEngine.calculate_state_hash(await engine.replay())
    h2 = ReplayEngine.calculate_state_hash(await engine.replay())
    h3 = ReplayEngine.calculate_state_hash(await engine.replay())
    
    assert h1 == h2 == h3
    
    # Verify State Content
    state = await engine.replay()
    assert state.positions[symbol].quantity == Decimal('0.5')
    assert state.positions[symbol].average_price == Decimal('50000.0')
    # Mid price 51050. PnL = (51050 - 50000) * 0.5 = 525
    assert state.positions[symbol].unrealized_pnl == Decimal('525.0')


@pytest.mark.asyncio
async def test_position_flipping_determinism(event_store):
    """Verify state reconstruction survives long-to-short flipping."""
    engine = ReplayEngine(event_store)
    symbol = "ETH/USDT"
    
    # 1. Go Long 1.0 @ 2000
    await event_store.append(FillEvent(
        trace_id=uuid.uuid4(), source="X", partition_key=symbol,
        payload=FillPayload(order_id="1", symbol=symbol, side="BUY", quantity=1.0, price=2000.0)
    ))
    
    # 2. Go Short 3.0 @ 2100 (Flip to -2.0)
    await event_store.append(FillEvent(
        trace_id=uuid.uuid4(), source="X", partition_key=symbol,
        payload=FillPayload(order_id="2", symbol=symbol, side="SELL", quantity=3.0, price=2100.0)
    ))
    
    state = await engine.replay()
    pos = state.positions[symbol]
    
    assert pos.quantity == Decimal('-2.0')
    assert pos.average_price == Decimal('2100.0') # New cost basis after flip


@pytest.mark.asyncio
async def test_replay_performance_benchmark(event_store):
    """Benchmark raw replay speed."""
    import time
    engine = ReplayEngine(event_store)
    num_events = 200
    
    for i in range(num_events):
        evt = MarketEvent(
            trace_id=uuid.uuid4(), source="Feed", partition_key="BENCH",
            payload=MarketPayload(symbol="BENCH", bid=i, ask=i+1)
        )
        await event_store.append(evt)
        
    t0 = time.perf_counter()
    state = await engine.replay()
    dt = time.perf_counter() - t0
    
    events_per_sec = num_events / dt
    print(f"\nReplay Performance: {events_per_sec:.2f} events/sec")
    assert events_per_sec > 500  # Conservative baseline
