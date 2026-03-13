import pytest

from qtrader.core.event import OrderEvent
from qtrader.execution.oms import UnifiedOMS
from qtrader.execution.sor import SmartOrderRouter


class _DummyAdapter:
    async def submit_order(self, order: OrderEvent) -> str:  # pragma: no cover
        raise RuntimeError("not used")

    async def cancel_order(self, order_id: str) -> bool:  # pragma: no cover
        return False

    async def get_fills(self, order_id: str):  # pragma: no cover
        return []

    async def get_balance(self) -> dict:  # pragma: no cover
        return {}


@pytest.mark.asyncio
async def test_sor_prefers_best_price_from_market_state() -> None:
    oms = UnifiedOMS()
    oms.add_venue("A", _DummyAdapter())
    oms.add_venue("B", _DummyAdapter())

    oms.update_market_state(
        "A",
        "BTC-USD",
        {"bid": 99.0, "ask": 101.0, "ask_size": 5.0},
    )
    oms.update_market_state(
        "B",
        "BTC-USD",
        {"bid": 98.0, "ask": 100.0, "ask_size": 1.0},
    )

    sor = SmartOrderRouter(oms)
    assert await sor.get_best_venue("BTC-USD", "BUY") == "B"

    oms.update_market_state(
        "A",
        "BTC-USD",
        {"bid": 99.0, "ask": 101.0, "bid_size": 1.0},
    )
    oms.update_market_state(
        "B",
        "BTC-USD",
        {"bid": 100.0, "ask": 102.0, "bid_size": 1.0},
    )
    assert await sor.get_best_venue("BTC-USD", "SELL") == "B"


@pytest.mark.asyncio
async def test_sor_tie_breaks_by_depth() -> None:
    oms = UnifiedOMS()
    oms.add_venue("A", _DummyAdapter())
    oms.add_venue("B", _DummyAdapter())

    # Same ask, different depth -> choose deeper.
    oms.update_market_state(
        "A",
        "ETH-USD",
        {"ask": 2000.0, "ask_size": 10.0},
    )
    oms.update_market_state(
        "B",
        "ETH-USD",
        {"ask": 2000.0, "ask_size": 1.0},
    )

    sor = SmartOrderRouter(oms)
    assert await sor.get_best_venue("ETH-USD", "BUY") == "A"


@pytest.mark.asyncio
async def test_sor_impact_based_selection() -> None:
    oms = UnifiedOMS()
    oms.add_venue("A", _DummyAdapter())
    oms.add_venue("B", _DummyAdapter())

    # Same ask price but different daily_volume => different impact.
    oms.update_market_state(
        "A",
        "BTC-USD",
        {
            "ask": 100.0,
            "ask_size": 1.0,
            "daily_volume": 1_000_000,
            "sigma_daily": 0.02,
        },
    )
    oms.update_market_state(
        "B",
        "BTC-USD",
        {
            "ask": 100.0,
            "ask_size": 1.0,
            "daily_volume": 10_000,
            "sigma_daily": 0.02,
        },
    )
    oms.set_pending_order_context("BTC-USD", {"order_size": 5000.0})

    sor = SmartOrderRouter(oms)
    assert await sor.get_best_venue("BTC-USD", "BUY") == "A"
