import asyncio
import os
import time
from datetime import datetime, timezone

from qtrader.core.event import EventType, DataRejectedEvent
from qtrader.core.event_bus import EventBus
from qtrader.oms.event_store import EventStore
# from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator
from qtrader.data.pipeline.normalizer import UnifiedNormalizer

# Since orchestrator is updated, we need to import it
from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator

async def test_quality_gate_simulation():
    # Setup - Clean state
    log_path = "/tmp/quality_gate_log.jsonl"
    if os.path.exists(log_path):
        os.remove(log_path)
    
    event_store = EventStore(log_path=log_path)
    bus = EventBus()
    
    # Track events
    rejections = []
    
    def on_rejected(event):
        rejections.append(event)
        print(f"GATE: Rejected {event.symbol} - {event.reason} (Value: {event.value})")
        
    bus.subscribe(EventType.DATA_REJECTED, on_rejected)
    await bus.start()
    
    orchestrator = MarketPipelineOrchestrator(
        event_bus=bus,
        event_store=event_store,
        normalizer=UnifiedNormalizer()
    )
    await orchestrator.start()

    print("\n--- Phase 1: Seeding Normal Data ---")
    for i in range(20):
        raw = {
            "venue": "binance",
            "symbol": "BTC-USDT",
            "seq_id": i + 1,
            "data": {"b": 50000 + i, "a": 50001 + i, "c": 50000.5 + i},
            "timestamp": time.time(),
            "trace_id": f"seed-{i}"
        }
        await orchestrator.process(raw)
    
    print(f"Verified: Seeded 20 events. EventStore contains {len(event_store.get_recent_prices('BTC-USDT'))} prices.")

    print("\n--- Phase 2: Injecting MAD Outlier (10x price) ---")
    outlier_raw = {
        "venue": "binance",
        "symbol": "BTC-USDT",
        "seq_id": 21,
        "data": {"b": 500000, "a": 500001, "c": 500005.0},
        "timestamp": time.time(),
        "trace_id": "outlier-1"
    }
    await orchestrator.process(outlier_raw)
    await asyncio.sleep(0.1)

    print("\n--- Phase 3: Injecting Cross-Exchange Deviation ---")
    # Seed a reference price from Coinbase
    cb_raw = {
        "venue": "coinbase",
        "symbol": "BTC-USDT",
        "seq_id": 22,
        "data": {"b": 50000, "a": 50001, "c": 50000.5},
        "timestamp": time.time(),
        "trace_id": "cb-ref"
    }
    await orchestrator.process(cb_raw)
    
    # Inject Binance price that deviates from Coinbase by 10% (threshold is 5%)
    deviant_raw = {
        "venue": "binance",
        "symbol": "BTC-USDT",
        "seq_id": 23,
        "data": {"b": 56000, "a": 56001, "c": 56000.5}, # ~12% deviation from 50000
        "timestamp": time.time(),
        "trace_id": "outlier-2"
    }
    await orchestrator.process(deviant_raw)
    await asyncio.sleep(0.1)

    print("\n--- Verification ---")
    if len(rejections) >= 2:
        print("SUCCESS: Both MAD outlier and Cross-Exchange deviation were blocked!")
    else:
        print(f"FAILED: Expected 2 rejections, got {len(rejections)}")

    await orchestrator.stop()
    await bus.stop()
    print("\nSimulation Complete")

if __name__ == "__main__":
    asyncio.run(test_quality_gate_simulation())
