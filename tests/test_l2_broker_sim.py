import pytest

from qtrader.backtest.l2_broker_sim import L2BrokerSim
from qtrader.core.event import FillEvent, MarketDataEvent, OrderEvent

SYMBOL = "BTC-USD"
BEST_BID = 100.0
BEST_ASK = 101.0
HIGH_ASK = 110.0
ASK_DEPTH = 1.0
BID_DEPTH = 1.0
EXPECTED_FILLS = 2


class _StubBus:
    def __init__(self) -> None:
        self.events: list[FillEvent] = []

    async def publish(self, event: FillEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_l2_sim_crossing_limit_buy_fills() -> None:
    bus = _StubBus()
    sim = L2BrokerSim(bus, latency_ms=0)  # type: ignore[arg-type]

    order = OrderEvent(
        symbol=SYMBOL,
        order_type="LIMIT",
        quantity=1.0,
        price=105.0,
        side="BUY",
    )
    await sim.on_order(order)

    md = MarketDataEvent(
        symbol=SYMBOL,
        data={
            "bid": BEST_BID,
            "ask": BEST_ASK,
            "bid_size": 5.0,
            "ask_size": 5.0,
        },
    )
    await sim.on_market_data(md)

    assert len(bus.events) == 1
    assert bus.events[0].symbol == SYMBOL
    assert bus.events[0].price == BEST_ASK


@pytest.mark.asyncio
async def test_l2_sim_trade_depletion_allows_fill_without_crossing() -> None:
    bus = _StubBus()
    sim = L2BrokerSim(bus, latency_ms=0)  # type: ignore[arg-type]

    # Limit buy below ask, so it won't cross. Fill should occur after volume_ahead is depleted.
    order = OrderEvent(
        symbol=SYMBOL,
        order_type="LIMIT",
        quantity=1.0,
        price=BEST_BID,
        side="BUY",
    )
    await sim.on_order(order)

    # Initial book: bid_size sets volume_ahead.
    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "bid": BEST_BID,
                "ask": HIGH_ASK,
                "bid_size": 2.0,
                "ask_size": 2.0,
            },
        )
    )
    assert len(bus.events) == 0

    # Trade at/under our limit consumes volume_ahead.
    # trade_qty >= volume_ahead => volume_ahead <= 0 => fill at limit.
    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "bid": BEST_BID,
                "ask": HIGH_ASK,
                "bid_size": 2.0,
                "ask_size": 2.0,
                "trade_price": BEST_BID,
                "trade_qty": 5.0,
                "trade_side": "SELL",
            },
        )
    )

    assert len(bus.events) == 1
    assert bus.events[0].price == BEST_BID


@pytest.mark.asyncio
async def test_l2_sim_partial_fills_from_trade_prints() -> None:
    bus = _StubBus()
    sim = L2BrokerSim(bus, latency_ms=0)  # type: ignore[arg-type]

    order = OrderEvent(
        symbol=SYMBOL,
        order_type="LIMIT",
        quantity=2.0,
        price=BEST_ASK,
        side="SELL",
        order_id="o1",
    )
    await sim.on_order(order)

    # Best ask at 101; BUY trades should consume asks.
    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "bid": BEST_BID,
                "ask": BEST_ASK,
                "bid_size": BID_DEPTH,
                "ask_size": ASK_DEPTH,
            },
        )
    )

    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "trade_price": BEST_ASK,
                "trade_qty": 1.0,
                "trade_side": "BUY",
            },
        )
    )
    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "trade_price": BEST_ASK,
                "trade_qty": 1.0,
                "trade_side": "BUY",
            },
        )
    )

    assert len(bus.events) == EXPECTED_FILLS
    assert bus.events[0].order_id == "o1"
    assert bus.events[1].order_id == "o1"


@pytest.mark.asyncio
async def test_l2_sim_price_time_priority_same_price() -> None:
    bus = _StubBus()
    sim = L2BrokerSim(bus, latency_ms=0)  # type: ignore[arg-type]

    o1 = OrderEvent(
        symbol=SYMBOL,
        order_type="LIMIT",
        quantity=1.0,
        price=BEST_ASK,
        side="SELL",
        order_id="o1",
    )
    o2 = OrderEvent(
        symbol=SYMBOL,
        order_type="LIMIT",
        quantity=1.0,
        price=BEST_ASK,
        side="SELL",
        order_id="o2",
    )

    await sim.on_order(o1)
    await sim.on_order(o2)

    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "bid": BEST_BID,
                "ask": BEST_ASK,
                "bid_size": BID_DEPTH,
                "ask_size": ASK_DEPTH,
            },
        )
    )
    await sim.on_market_data(
        MarketDataEvent(
            symbol=SYMBOL,
            data={
                "trade_price": BEST_ASK,
                "trade_qty": 1.0,
                "trade_side": "BUY",
            },
        )
    )

    assert len(bus.events) == 1
    assert bus.events[0].order_id == "o1"


@pytest.mark.asyncio
async def test_l2_sim_schema_missing_keys_does_not_crash() -> None:
    bus = _StubBus()
    sim = L2BrokerSim(bus, latency_ms=0)  # type: ignore[arg-type]
    await sim.on_market_data(MarketDataEvent(symbol=SYMBOL, data={}))
    assert len(bus.events) == 0
