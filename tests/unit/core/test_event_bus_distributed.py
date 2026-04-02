import asyncio
import time
import uuid

import pytest

from qtrader.core.event_bus import EventBus
from qtrader.core.event_store import FileEventStore
from qtrader.core.events import BaseEvent, EventType, MarketEvent, MarketPayload


@pytest.fixture
async def event_bus():
    store = FileEventStore(log_path="data/test_event_store.jsonl")
    bus = EventBus(num_partitions=4, event_store=store)
    await bus.start()
    yield bus
    await bus.stop()


@pytest.mark.asyncio
async def test_partitioned_ordering(event_bus):
    """Verify that events for the same symbol are delivered in strict chronological order."""
    symbol = "BTC/USDT"
    received_seq_ids = []
    
    async def handler(event: MarketEvent):
        # Simulate slight processing delay to test if order holds
        await asyncio.sleep(0.001)
        received_seq_ids.append(event.payload.seq_id)
        
    event_bus.subscribe(EventType.MARKET_DATA, handler)
    
    # Publish 50 events for the same symbol
    for i in range(50):
        payload = MarketPayload(symbol=symbol, bid=50000.0 + i, ask=50001.0 + i, seq_id=i)
        event = MarketEvent(
            trace_id=uuid.uuid4(),
            source="TestManual",
            payload=payload
        )
        await event_bus.publish(event)
        
    # Wait for processing
    await asyncio.sleep(0.5)
    
    # Assert sequence is strictly 0 to 49
    assert received_seq_ids == list(range(50))


@pytest.mark.asyncio
async def test_distributed_throughput(event_bus):
    """Verify throughput of the event bus under load."""
    total_events = 1000
    start_time = time.perf_counter()
    
    async def fast_handler(event: BaseEvent):
        pass
        
    event_bus.subscribe(EventType.MARKET_DATA, fast_handler)
    
    for i in range(total_events):
        payload = MarketPayload(symbol=f"SYM_{i%10}", bid=1.0, ask=1.1, seq_id=i)
        event = MarketEvent(trace_id=uuid.uuid4(), source="Bench", payload=payload)
        await event_bus.publish(event)
        
    await asyncio.sleep(0.2) # Allow processing time
    
    duration = time.perf_counter() - start_time
    throughput = total_events / duration
    print(f"\nThroughput: {throughput:.2f} events/sec")
    
    assert throughput > 1000  # Local test baseline, CI might be slower but should be high


@pytest.mark.asyncio
async def test_backpressure_dropping(event_bus):
    """Verify that low priority events are dropped under heavy partition load."""
    # We'll fill one partition's queue manually to simulate load
    # Note: EventBus partitions by key. We'll use the same symbol.
    symbol = "HOT_SYMBOL"
    
    # Subscribe with a slow handler to build up the queue
    async def slow_handler(event):
        await asyncio.sleep(0.1)
        
    event_bus.subscribe(EventType.HEARTBEAT, slow_handler)
    
    # Publish many HEARTBEAT (LOW priority) events
    dropped = 0
    for i in range(2500): # Exceeds warning threshold (2000)
        event = BaseEvent(
            trace_id=uuid.uuid4(),
            source="LoadTest",
            event_type=EventType.HEARTBEAT,
            payload={"symbol": symbol}
        )
        success = await event_bus.publish(event)
        if not success:
            dropped += 1
            
    assert dropped > 0
    print(f"Correctly dropped {dropped} low-priority events under pressure.")
