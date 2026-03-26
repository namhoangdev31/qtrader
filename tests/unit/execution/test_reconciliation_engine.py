import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from qtrader.core.event import EventType, FillEvent, TradingHaltEvent
from qtrader.core.event_bus import EventBus
from qtrader.core.state_store import StateStore, Position
from qtrader.oms.order_management_system import UnifiedOMS
from qtrader.execution.reconciliation_engine import ReconciliationEngine


class MockExchange:
    def __init__(self, positions):
        self.positions = positions

    async def get_balance(self):
        return self.positions


@pytest.mark.asyncio
async def test_reconciliation_engine_halts_on_mismatch():
    event_bus = EventBus()
    state_store = StateStore()
    oms = UnifiedOMS(state_store, event_bus)
    
    # Configure mock exchange adapter
    mock_adapter = MockExchange({"BTC": 1.5})
    oms.add_venue("binance", mock_adapter)

    engine = ReconciliationEngine(event_bus, oms, state_store)
    await engine.start()
    
    # Track halts
    halts = []
    async def on_halt(e):
        halts.append(e)
    event_bus.subscribe(EventType.TRADING_HALT, on_halt)
    
    # Populate internal state
    await state_store.set_position(Position(symbol="BTC/USD", quantity=Decimal('1.0'), average_price=Decimal('10000')))

    # Trigger via fill event
    fill_event = FillEvent(
        order_id="123", symbol="BTC/USD", side="BUY", quantity=0.0, price=0.0, timestamp=None
    )
    
    # Reconcilation engine will see StateStore (BTC=1.0) vs Exchange (BTC=1.5). Differene = -0.5
    # Should trigger halt
    await event_bus.start()
    await event_bus.publish(EventType.FILL, fill_event)
    await asyncio.sleep(0.2) # Wait for engine logic
    
    assert len(halts) == 1
    assert halts[0].reason == "POSITION_MISMATCH"
