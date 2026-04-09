from __future__ import annotations
import time
from decimal import Decimal
import pytest
from qtrader.execution.market_maker import (
    InventoryState,
    MarketMakerConfig,
    MarketMakerEngine,
    Quote,
)


@pytest.fixture
def engine() -> MarketMakerEngine:
    return MarketMakerEngine(
        MarketMakerConfig(
            gamma=0.1,
            k=1.5,
            max_inventory=10.0,
            max_spread_bps=100.0,
            min_spread_bps=5.0,
            toxicity_withdrawal_threshold=0.75,
            toxicity_widen_threshold=0.5,
        )
    )


class TestMarketMakerEngine:
    def test_compute_quotes_basic(self, engine: MarketMakerEngine) -> None:
        quote = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02, toxicity_score=0.0
        )
        assert quote is not None
        assert quote.bid_price < quote.ask_price
        assert quote.spread_bps >= 5.0
        assert quote.spread_bps <= 100.0

    def test_toxicity_withdrawal(self, engine: MarketMakerEngine) -> None:
        quote = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02, toxicity_score=0.8
        )
        assert quote is None

    def test_toxicity_widens_spread(self, engine: MarketMakerEngine) -> None:
        quote_normal = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02, toxicity_score=0.0
        )
        quote_toxic = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02, toxicity_score=0.6
        )
        assert quote_normal is not None
        assert quote_toxic is not None
        assert quote_toxic.spread_bps >= quote_normal.spread_bps

    def test_inventory_skew(self, engine: MarketMakerEngine) -> None:
        inv = engine.update_inventory("BTC-USDT", Decimal("50000"), Decimal("1.0"), "BUY")
        assert inv.position == Decimal("1.0")
        quote_long = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02
        )
        quote_flat = engine.compute_quotes(
            symbol="ETH-USDT", mid_price=Decimal("50000"), volatility=0.02
        )
        assert quote_long is not None
        assert quote_flat is not None
        assert quote_long.reservation_price < quote_flat.reservation_price

    def test_inventory_state(self, engine: MarketMakerEngine) -> None:
        inv = engine.get_or_create_inventory("BTC-USDT")
        assert inv.position == Decimal("0")
        assert inv.skew_direction == 0
        engine.update_inventory("BTC-USDT", Decimal("50000"), Decimal("1.0"), "BUY")
        inv = engine.get_or_create_inventory("BTC-USDT")
        assert inv.position == Decimal("1.0")
        assert inv.skew_direction == -1
        engine.update_inventory("BTC-USDT", Decimal("50000"), Decimal("2.0"), "SELL")
        inv = engine.get_or_create_inventory("BTC-USDT")
        assert inv.position == Decimal("-1.0")
        assert inv.skew_direction == 1

    def test_quote_lifecycle(self, engine: MarketMakerEngine) -> None:
        quote = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02
        )
        assert quote is not None
        engine.register_quote(quote)
        assert "BTC-USDT" in engine._active_quotes
        engine.withdraw_quote("BTC-USDT")
        assert "BTC-USDT" not in engine._active_quotes

    def test_should_update_quote(self, engine: MarketMakerEngine) -> None:
        assert engine.should_update_quote("BTC-USDT")
        quote = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02
        )
        if quote:
            engine.register_quote(quote)
        assert not engine.should_update_quote("BTC-USDT")

    def test_telemetry(self, engine: MarketMakerEngine) -> None:
        engine.compute_quotes("BTC-USDT", Decimal("50000"), 0.02)
        engine.compute_quotes("BTC-USDT", Decimal("50000"), 0.02, toxicity_score=0.8)
        engine.update_inventory("BTC-USDT", Decimal("50000"), Decimal("1.0"), "BUY")
        telemetry = engine.get_telemetry()
        assert telemetry["quote_count"] >= 1
        assert telemetry["withdrawal_count"] >= 1
        assert telemetry["fill_count"] == 1

    def test_inventory_summary(self, engine: MarketMakerEngine) -> None:
        engine.update_inventory("BTC-USDT", Decimal("50000"), Decimal("1.0"), "BUY")
        summary = engine.get_inventory_summary()
        assert "BTC-USDT" in summary
        assert summary["BTC-USDT"]["position"] == 1.0

    def test_active_quotes(self, engine: MarketMakerEngine) -> None:
        quote = engine.compute_quotes(
            symbol="BTC-USDT", mid_price=Decimal("50000"), volatility=0.02
        )
        if quote:
            engine.register_quote(quote)
        active = engine.get_active_quotes()
        assert "BTC-USDT" in active
        assert "bid" in active["BTC-USDT"]
        assert "ask" in active["BTC-USDT"]
