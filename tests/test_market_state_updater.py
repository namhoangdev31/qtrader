import asyncio

import pytest

from qtrader.core.bus import EventBus
from qtrader.core.event import EventType, MarketDataEvent, OrderEvent
from qtrader.execution.market_state import MarketStateUpdater
from qtrader.execution.oms import UnifiedOMS
from qtrader.execution.sor import SmartOrderRouter


class _DummyAdapter:
    async def submit_order(self, order: OrderEvent) -> str:  # pragma: no cover
        return "oid"

    async def cancel_order(self, order_id: str) -> bool:  # pragma: no cover
        return False

    async def get_fills(self, order_id: str):  # pragma: no cover
        return []

    async def get_balance(self) -> dict:  # pragma: no cover
        return {"USDT": 0.0}


@pytest.mark.asyncio
async def test_market_state_updater_updates_oms_and_sor_uses_it() -> None:
    bus = EventBus(queue_maxsize=10)
    oms = UnifiedOMS()
    oms.add_venue("coinbase", _DummyAdapter())
    oms.add_venue("binance", _DummyAdapter())

    updater = MarketStateUpdater(oms, default_venue="coinbase")
    bus.subscribe(EventType.MARKET_DATA, updater.on_market_data)  # type: ignore[arg-type]

    task = asyncio.create_task(bus.start())

    await bus.publish(
        MarketDataEvent(
            symbol="BTC-USD",
            data={"venue": "coinbase", "bid": 99.0, "ask": 101.0, "bid_size": 1.0, "ask_size": 1.0},
        )
    )
    await bus.publish(
        MarketDataEvent(
            symbol="BTC-USD",
            data={"venue": "binance", "bid": 98.0, "ask": 100.0, "bid_size": 1.0, "ask_size": 1.0},
        )
    )

    await asyncio.sleep(0.05)
    sor = SmartOrderRouter(oms)
    assert await sor.get_best_venue("BTC-USD", "BUY") == "binance"

    await bus.shutdown()
    await asyncio.wait_for(task, timeout=1.0)

