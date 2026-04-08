import asyncio
import logging
from decimal import Decimal
from qtrader.core.event_bus import EventBus
from qtrader.core.events import MarketEvent, MarketPayload, EventType, SystemEvent, SystemPayload
from qtrader.execution.paper_engine import PaperTradingEngine
from qtrader.core.forensic_auditor import ForensicAuditor
from unittest.mock import MagicMock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smoke_test")

async def run_smoke_test():
    logger.info("Starting Event-Driven Simulation Smoke Test...")
    
    # 1. Setup EventBus and Mocks
    bus = EventBus()
    db_writer = MagicMock()
    db_writer.write_forensic_note = AsyncMock()
    
    # 2. Initialize Engine and Auditor
    # Engine now pulls many settings from config.py automatically
    engine = PaperTradingEngine(starting_capital=10000.0, base_price=50000.0)
    engine.set_event_bus(bus)
    
    auditor = ForensicAuditor(bus, db_writer, session_id="smoke-test-session")
    auditor.start()
    
    # Subscribe engine to market data manually for the test
    bus.subscribe(EventType.MARKET_DATA, engine.handle_market_event)

    # 3. Simulate Price Tick
    logger.info("Injecting MarketEvent @ $50100")
    event = MarketEvent(
        source="test",
        payload=MarketPayload(
            symbol="BTC-USD",
            data={"price": 50100.0},
            bid=Decimal("50095.0"),
            ask=Decimal("50105.0")
        )
    )
    
    # Drive the simulation tick
    await bus.publish(event)
    await asyncio.sleep(0.05) # Delay for event propagation
    
    logger.info(f"Engine Price: {engine._current_price}")
    assert engine._current_price == 50100.0, "Engine price should have updated on Event"
    
    # 4. Force a Signal/Position to check Forensic Audit
    logger.info("Forcing a signal to verify ForensicAuditor capture...")
    # Mocking generation to ensure a BUY signal
    engine._generate_signal = MagicMock(return_value={"action": "BUY", "strength": 0.9})
    
    # Another market tick to trigger signal check
    await bus.publish(event)
    await asyncio.sleep(0.05)
    
    # Check if a position was opened
    assert "BTC-USD" in engine._managed_positions, "Position should have opened on strong signal"
    
    # 5. Verify Forensic Auditor Output
    # Wait for async DB writes and re-publications
    await asyncio.sleep(0.1)
    
    assert db_writer.write_forensic_note.called, "Forensic Auditor should have persisted the signal"
    
    # Check format: [ALPHA] {model_id} generated {action} signal...
    calls = db_writer.write_forensic_note.call_args_list
    signal_note = next(c for c in calls if "[ALPHA]" in c[1]["content"])
    content = signal_note[1]["content"]
    
    logger.info(f"Captured Forensic Note: {content}")
    assert "[ALPHA]" in content
    assert "generated BUY signal" in content
    assert "Confidence:" in content 
    
    # 6. Verify System/OMS Rejection capture
    logger.info("Injecting SystemEvent (ORDER_REJECTED) to verify OMS auditing...")
    rejection_event = SystemEvent(
        source="UnifiedOMS",
        payload=SystemPayload(
            action="ORDER_REJECTED",
            reason="Insufficient Liquidity",
            metadata={"order_id": "ORD-SMOKE-1"}
        )
    )
    await bus.publish(rejection_event)
    await asyncio.sleep(0.1)
    
    calls = db_writer.write_forensic_note.call_args_list
    oms_note = next(c for c in calls if "[OMS]" in c[1]["content"])
    logger.info(f"Captured OMS Rejection: {oms_note[1]['content']}")
    assert "Insufficient Liquidity" in oms_note[1]['content']

    logger.info("Smoke Test PASSED: Hardened Forensic Auditing verified.")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
