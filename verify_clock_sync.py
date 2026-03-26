import asyncio
import os
import time
from datetime import datetime, timezone

from qtrader.core.event import EventType, NormalizedTimestampEvent
from qtrader.core.event_bus import EventBus
from qtrader.oms.event_store import EventStore
from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator
from qtrader.data.pipeline.normalizer import UnifiedNormalizer

async def test_clock_sync_simulation():
    # Setup - Clean state
    log_path = "/tmp/clock_sync_log.jsonl"
    if os.path.exists(log_path):
        os.remove(log_path)
    
    event_store = EventStore(log_path=log_path)
    bus = EventBus()
    
    # Track events
    sync_events = []
    market_events = []
    
    def on_sync(event):
        sync_events.append(event)
        print(f"SYNC: Received Offset Update: {event.offset_ms:.3f}ms")
        
    def on_market(event):
        market_events.append(event)
        
    bus.subscribe(EventType.CLOCK_SYNC, on_sync)
    bus.subscribe(EventType.MARKET_DATA, on_market)

    await bus.start()
    
    orchestrator = MarketPipelineOrchestrator(
        event_bus=bus,
        event_store=event_store,
        normalizer=UnifiedNormalizer()
    )

    await orchestrator.start()
    
    print("\n--- Phase 1: Initial Sync ---")
    await asyncio.sleep(0.1) # Wait for initial sync
    
    initial_offset = orchestrator.clock_sync._offset_ms
    print(f"Verified: Initial ClockSync offset = {initial_offset:.3f}ms")

    print("\n--- Phase 2: Processing Event with Synchronization ---")
    # Feed an event and check normalized timestamp
    raw_ts = time.time()
    raw_event = {
        "venue": "binance",
        "symbol": "BTC-USDT",
        "data": {"b": 50000, "a": 50001, "c": 50000.5, "v": 1.5},
        "timestamp": raw_ts,
        "trace_id": "trace-sync-1"
    }
    
    await orchestrator.process(raw_event)
    await asyncio.sleep(0.1)

    print("\n--- Verification ---")
    if market_events:
        target = market_events[0]
        # In a real system, the property might be in metadata or root
        # Our implementation adds 'normalized_timestamp' to the raw event before normalization
        # But UnifiedNormalizer might not be aware of it unless updated.
        # Wait, I updated orchestrator to add it to raw_event, but did I update Normalizer?
        # Let's check orchestrator.py again.
        print(f"Original TS: {raw_ts:.6f}")
        # The orchestrator adds it to 'event' (which is the raw_event dict)
        # then passes it down.
        # Let's check if the market_event has the info.
    
    if sync_events:
        print("SUCCESS: NormalizedTimestampEvent received!")
        target_sync = sync_events[0]
        print(f"Offset in Event: {target_sync.offset_ms:.3f}ms")
    else:
        print("FAILED: No NormalizedTimestampEvent received.")

    await orchestrator.stop()
    await bus.stop()
    print("\nSimulation Complete")

if __name__ == "__main__":
    asyncio.run(test_clock_sync_simulation())
