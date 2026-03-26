import asyncio
import os
import shutil
import time
from datetime import datetime

from qtrader.core.event import EventType, MarketDeltaEvent, GapFreeMarketEvent
from qtrader.core.event_bus import EventBus
from qtrader.oms.event_store import EventStore
from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator
from qtrader.data.pipeline.normalizer import UnifiedNormalizer

async def test_recovery_simulation():
    # Setup - Clean state
    log_path = "/tmp/market_event_log.jsonl"
    if os.path.exists(log_path):
        os.remove(log_path)
    
    event_store = EventStore(log_path=log_path)
    bus = EventBus()
    
    # Track events
    received_events = []
    def on_market_event(event):
        received_events.append(event)
        
    bus.subscribe(EventType.MARKET_DATA, on_market_event)
    bus.subscribe(EventType.GAP_FREE_MARKET, on_market_event)
    bus.subscribe(EventType.GAP_DETECTED, lambda e: print(f"DETECTOR: Gap Detected! Expected {e.expected_seq}, Got {e.received_seq}"))
    bus.subscribe(EventType.RECOVERY_COMPLETED, lambda e: print(f"RECOVERY: State Recomputed up to {e.recovered_seq}"))

    await bus.start()
    
    orchestrator = MarketPipelineOrchestrator(
        event_bus=bus,
        event_store=event_store,
        normalizer=UnifiedNormalizer()
    )

    print("\n--- Phase 1: Normal Ticks ---")
    # Feed initial events to establish sequence
    for i in range(1, 101):
        raw = {
            "venue": "binance",
            "symbol": "BTC-USDT",
            "seq_id": i,
            "data": {"b": 50000 + i, "a": 50001 + i, "c": 50000.5 + i, "v": 1.5},
            "trace_id": f"trace-{i}"
        }
        await orchestrator.process(raw)
    
    print(f"Verified: EventStore last_seq = {event_store.get_last_sequence('BTC-USDT')}")

    print("\n--- Phase 2: Injecting Gap (Skip 101-104, send 105) ---")
    raw_gap = {
        "venue": "binance",
        "symbol": "BTC-USDT",
        "seq_id": 105,
        "data": {"b": 51000, "a": 51001, "c": 51000.5, "v": 2.0},
        "trace_id": "trace-gap-105"
    }
    
    await orchestrator.process(raw_gap)
    await asyncio.sleep(0.1) # Wait for async processing

    print("\n--- Verification ---")
    if any(isinstance(e, GapFreeMarketEvent) for e in received_events):
        print("SUCCESS: GapFreeMarketEvent received!")
        target = [e for e in received_events if isinstance(e, GapFreeMarketEvent)][0]
        print(f"Reconstructed Seq: {target.seq_id}")
        print(f"Bids count: {len(target.bids)}")
    else:
        print("FAILED: No GapFreeMarketEvent received.")

    await bus.stop()
    print("\nSimulation Complete")

if __name__ == "__main__":
    asyncio.run(test_recovery_simulation())
