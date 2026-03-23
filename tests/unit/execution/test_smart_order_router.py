"""
Level 1 Critical Tests for SmartOrderRouter (execution/smart_router.py)
Covers: best price routing, smart routing, order splitting, latency/fee factors.
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from qtrader.execution.smart_router import SmartOrderRouter
from qtrader.core.types import OrderEvent  # Adjust import as needed


def make_order(order_id="o1", symbol="BTC", side="BUY", quantity=Decimal("1.0"),
               order_type="MARKET", price=None, metadata=None):
    return OrderEvent(
        order_id=order_id,
        symbol=symbol,
        timestamp=datetime.utcnow(),
        order_type=order_type,
        side=side,
        quantity=quantity,
        price=price,
        metadata=metadata or {},
    )


def make_market_data(binance_ask="50000", binance_bid="49990",
                     coinbase_ask="49900", coinbase_bid="49980",
                     binance_qty="1.0", coinbase_qty="1.0"):
    return {
        "binance": {
            "bids": [[binance_bid, binance_qty]],
            "asks": [[binance_ask, binance_qty]],
        },
        "coinbase": {
            "bids": [[coinbase_bid, coinbase_qty]],
            "asks": [[coinbase_ask, coinbase_qty]],
        },
    }


@pytest.fixture
def two_exchange_router():
    exchanges = {"binance": MagicMock(), "coinbase": MagicMock()}
    return SmartOrderRouter(exchanges=exchanges, routing_mode="best_price")


# ---------------------------------------------------------------------------
# Best-price routing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_best_price_buy_selects_cheapest_ask(two_exchange_router):
    """BUY → choose the exchange with the lowest ask price."""
    order = make_order(side="BUY")
    market = make_market_data(binance_ask="50000", coinbase_ask="49900")
    routed = await two_exchange_router.route_order(order, market)

    assert len(routed) == 1
    assert routed[0].metadata["exchange"] == "coinbase"


@pytest.mark.asyncio
async def test_best_price_sell_selects_highest_bid(two_exchange_router):
    """SELL → choose the exchange with the highest bid price."""
    order = make_order(side="SELL")
    market = make_market_data(binance_bid="49990", coinbase_bid="49980")
    routed = await two_exchange_router.route_order(order, market)

    assert len(routed) == 1
    assert routed[0].metadata["exchange"] == "binance"


@pytest.mark.asyncio
async def test_best_price_empty_orderbook_fallback(two_exchange_router):
    """If one exchange has no asks/bids, fallback to the valid one."""
    order = make_order(side="BUY")
    market = {
        "binance": {"bids": [], "asks": []},     # empty book
        "coinbase": {"bids": [["49900", "1"]], "asks": [["49950", "1"]]},
    }
    routed = await two_exchange_router.route_order(order, market)
    assert len(routed) == 1
    assert routed[0].metadata["exchange"] == "coinbase"


@pytest.mark.asyncio
async def test_routing_sets_exchange_metadata(two_exchange_router):
    """Routed orders must carry 'exchange' key in metadata for downstream OMS."""
    order = make_order(side="BUY")
    market = make_market_data()
    routed = await two_exchange_router.route_order(order, market)
    assert "exchange" in routed[0].metadata
    assert "routed_at" in routed[0].metadata


# ---------------------------------------------------------------------------
# Smart routing (price × liquidity × fees × latency)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_smart_routing_penalises_high_fee():
    """Smart router should prefer a cheaper exchange even with slightly worse price when fees differ."""
    exchanges = {"hfee_ex": MagicMock(), "lfee_ex": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="smart")

    order = make_order(side="BUY")
    market = {
        "hfee_ex": {"bids": [["49990", "10"]], "asks": [["50000", "10"]]},
        "lfee_ex": {"bids": [["49980", "10"]], "asks": [["50010", "10"]]},  # slightly worse price
    }
    fees = {
        "hfee_ex": {"maker": Decimal("0.001"), "taker": Decimal("0.01")},  # high fee
        "lfee_ex": {"maker": Decimal("0.0001"), "taker": Decimal("0.0001")},  # very low fee
    }
    routed = await router.route_order(order, market, fees_data=fees)
    assert len(routed) == 1
    # With a 10× fee difference, lfee_ex should win despite slightly worse ask price
    assert routed[0].metadata["exchange"] == "lfee_ex"


@pytest.mark.asyncio
async def test_smart_routing_penalises_high_latency():
    """Smart router should prefer lower-latency exchange when other factors are equal."""
    exchanges = {"slow_ex": MagicMock(), "fast_ex": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="smart")

    order = make_order(side="BUY")
    market = {
        "slow_ex": {"bids": [["50000", "10"]], "asks": [["50000", "10"]]},
        "fast_ex": {"bids": [["50000", "10"]], "asks": [["50000", "10"]]},
    }
    latency = {"slow_ex": 0.9, "fast_ex": 0.01}
    routed = await router.route_order(order, market, latency_data=latency)
    assert routed[0].metadata["exchange"] == "fast_ex"


# ---------------------------------------------------------------------------
# Manual routing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_routing_respects_exchange_in_metadata():
    exchanges = {"binance": MagicMock(), "coinbase": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="manual")

    order = make_order(side="BUY", metadata={"exchange": "coinbase"})
    market = make_market_data()
    routed = await router.route_order(order, market)

    assert routed[0].metadata["exchange"] == "coinbase"


@pytest.mark.asyncio
async def test_manual_routing_unknown_exchange_fallback():
    """If no exchange in metadata, fallback silently to the first exchange."""
    exchanges = {"binance": MagicMock(), "coinbase": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="manual")

    order = make_order(side="BUY", metadata={})
    market = make_market_data()
    routed = await router.route_order(order, market)

    assert routed[0].metadata["exchange"] in ("binance", "coinbase")


# ---------------------------------------------------------------------------
# Order splitting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_splitting_creates_correct_slices():
    """Large orders must be sliced into ceil(qty / split_size) child orders."""
    exchanges = {"binance": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="best_price",
                               max_order_size=Decimal("2.0"), split_size=Decimal("2.0"))

    order = make_order(side="BUY", quantity=Decimal("5.0"))
    market = {"binance": {"bids": [["50000", "10"]], "asks": [["50000", "10"]]}}
    routed = await router.route_order(order, market)

    # 5 / 2 = 3 slices (2 + 2 + 1)
    assert len(routed) == 3
    total_qty = sum(o.quantity for o in routed)
    assert total_qty == Decimal("5.0")


@pytest.mark.asyncio
async def test_order_splitting_attaches_slice_metadata():
    exchanges = {"binance": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="best_price",
                               max_order_size=Decimal("1.0"), split_size=Decimal("1.0"))
    order = make_order(side="BUY", quantity=Decimal("3.0"))
    market = {"binance": {"bids": [["49000", "10"]], "asks": [["50000", "10"]]}}
    routed = await router.route_order(order, market)

    for i, child in enumerate(routed):
        assert child.metadata.get("is_slice") is True
        assert child.metadata.get("parent_order_id") == "o1"


@pytest.mark.asyncio
async def test_no_split_below_max_order_size():
    exchanges = {"binance": MagicMock()}
    router = SmartOrderRouter(exchanges=exchanges, routing_mode="best_price",
                               max_order_size=Decimal("10.0"))
    order = make_order(side="BUY", quantity=Decimal("3.0"))
    market = {"binance": {"bids": [["50000", "10"]], "asks": [["50000", "10"]]}}
    routed = await router.route_order(order, market)

    assert len(routed) == 1
    assert routed[0].metadata.get("is_slice") is not True
