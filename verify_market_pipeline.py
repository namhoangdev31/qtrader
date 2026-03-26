import asyncio
import time
from decimal import Decimal

from qtrader.core.event import EventType, MarketDataEvent
from qtrader.core.event_bus import EventBus
from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator
from qtrader.data.pipeline.arbitrator import Arbitrator
from qtrader.data.pipeline.gap_detector import GapDetector
from qtrader.data.pipeline.recovery import RecoveryService
from qtrader.data.pipeline.normalizer import UnifiedNormalizer
from qtrader.data.quality_gate import DataQualityGate


async def test_market_pipeline():
    """Simulate a market data event passing through the full pipeline."""
    bus = EventBus()
    
    # Subscribe to capture final emitted event
    captured_events = []
    def on_event(event):
        captured_events.append(event)
        
    bus.subscribe(EventType.MARKET_DATA, on_event)
    await bus.start()
    
    # Initialize Orchestrator with all stages
    orchestrator = MarketPipelineOrchestrator(
        event_bus=bus,
        normalizer=UnifiedNormalizer(),
        arbitrator=Arbitrator(primary_feed="A"),
        gap_detector=GapDetector(),
        recovery_service=RecoveryService(),
        quality_gate=DataQualityGate(),
    )
    
    # Case 1: Standard event
    raw_event = {
        "venue": "coinbase",
        "symbol": "BTC-USD",
        "bid": 50000.0,
        "ask": 50001.0,
        "last_price": 50000.5,
        "seq_id": 100,
        "trace_id": "test_trace_1"
    }
    
    print("\n--- Case 1: Normal Event ---")
    await orchestrator.process(raw_event)
    await asyncio.sleep(0.1)  # Wait for event bus
    
    if captured_events:
        event = captured_events[-1]
        print(f"Captured: {event.symbol} @ {event.price} (Trace: {event.trace_id})")
        assert event.symbol == "BTC-USD"
        assert event.price == 50000.5
    else:
        print("FAIL: No event captured")

    # Case 2: Gap Detection & Recovery
    raw_event_gap = {
        "venue": "coinbase",
        "symbol": "BTC-USD",
        "bid": 50010.0,
        "ask": 50011.0,
        "last_price": 50010.5,
        "seq_id": 105,  # Gap of 4 (101, 102, 103, 104)
        "trace_id": "test_trace_gap"
    }
    
    print("\n--- Case 2: Gap Event ---")
    await orchestrator.process(raw_event_gap)
    await asyncio.sleep(0.1)
    
    if len(captured_events) > 1:
        event = captured_events[-1]
        print(f"Captured Gap Event: {event.symbol} @ {event.price}")
        # Metadata check
        print(f"Metadata: {event.metadata}")
    
    # Case 3: Quality Gate Failure (Price Inversion)
    raw_event_bad = {
        "venue": "coinbase",
        "symbol": "BTC-USD",
        "bid": 60000.0,
        "ask": 50000.0,  # Inverted!
        "last_price": 55000.0,
        "seq_id": 106,
        "trace_id": "test_trace_bad"
    }
    
    # Capture errors
    error_events = []
    bus.subscribe(EventType.DATA_ERROR, lambda e: error_events.append(e))
    
    print("\n--- Case 3: Quality Failure ---")
    await orchestrator.process(raw_event_bad)
    await asyncio.sleep(0.1)
    
    if error_events:
        err = error_events[-1]
        print(f"Captured Expected Error: {err.source} - {err.message}")
    else:
        print("FAIL: No error captured for price inversion")

    await bus.stop()
    print("\nSimulation Complete")


if __name__ == "__main__":
    asyncio.run(test_market_pipeline())
