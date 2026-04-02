import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.event import EventType, OrderEvent, RetryOrderEvent
from qtrader.core.event_bus import EventBus
from qtrader.execution.execution_engine import (
    ExchangeAdapter,
    ExecutionEngine,
    SimulatedExchangeAdapter,
)


class MockFailingExchange(ExchangeAdapter):
    def __init__(self):
        super().__init__("MockFailingExchange")
        self.fail_count = 0
        self.calls = 0
        
    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        self.calls += 1
        if self.fail_count > 0:
            self.fail_count -= 1
            return False, "Simulated exchange failure"
        return True, "SUCCESS_ID"
        
    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        return True, None
        
    async def get_position(self, symbol: str) -> Decimal:
        return Decimal('0')


@pytest.mark.asyncio
async def test_execution_engine_retry_trigger():
    """Simulate failure -> retry triggered."""
    event_bus = EventBus()
    exchange = MockFailingExchange()
    exchange.fail_count = 1  # Fail once then succeed
    
    engine = ExecutionEngine(
        exchange_adapter=exchange,
        event_bus=event_bus,
        max_retry_attempts=3
    )
    
    # Track emitted retries
    retries = []
    async def track_retry(event: RetryOrderEvent):
        retries.append(event)
        
    event_bus.subscribe(EventType.RETRY_ORDER, track_retry)
    await event_bus.start()
    
    # It fails on attempt 1, triggering RETRY_ORDER
    order = OrderEvent(
        order_id="TEST_1",
        symbol="BTC/USD",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal('1.0'),
        price=None,
        timestamp=datetime.utcnow()
    )
    
    success, result = await engine.execute_order(order, attempt=1)
    
    # Engine failed to send so it returns False and emits retry event
    assert not success
    assert result is None
    
    # Wait for event bus
    await asyncio.sleep(0.05)
    
    # Assert retry was triggered
    assert len(retries) == 1
    assert retries[0].order.order_id == "TEST_1"
    assert retries[0].attempt == 2
