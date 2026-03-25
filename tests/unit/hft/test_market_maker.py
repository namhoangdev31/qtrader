import polars as pl
import pytest

from qtrader.hft.market_maker import AvellanedaStoikovMarketMaker

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

TEST_DATA = pl.DataFrame(
    {
        "micro_price": [100.0, 100.0, 100.0],
        "volatility": [1.0, 1.0, 1.0],
        "inventory": [0, 10, -10],
    }
)

# Configuration for unit tests
GAMMA = 0.1
K_INTENSITY = 1.5


def test_market_maker_neutral_inventory() -> None:
    """Verify market maker quotes for neutral (zero) inventory."""
    mm = AvellanedaStoikovMarketMaker(gamma=GAMMA, k=K_INTENSITY)
    quotes = mm.compute_quotes(TEST_DATA)

    # First row: inventory = 0
    # r = 100 - (0 * 0.1 * 1.0) = 100.0
    # spread_risk = 0.1 * 1.0 = 0.1
    # spread_intensity = (2/0.1) * ln(1 + 0.1/1.5) = 20 * ln(1.0666) ≈ 20 * 0.0645 = 1.290
    # delta = 0.1 + 1.290 = 1.390
    # bid = 100 - 0.695 = 99.305, ask = 100 + 0.695 = 100.695
    expected_rows = 3
    assert len(quotes) == expected_rows
    assert quotes[0]["bid_quote"].item() == pytest.approx(99.305, rel=1e-3)
    assert quotes[0]["ask_quote"].item() == pytest.approx(100.695, rel=1e-3)


def test_market_maker_inventory_asymmetry() -> None:
    """Verify that quotes tilt to reduce risk when inventory is high/low."""
    mm = AvellanedaStoikovMarketMaker(gamma=GAMMA, k=K_INTENSITY)
    quotes = mm.compute_quotes(TEST_DATA)

    # Row 1: Long inventory (+10) -> Reservation price shifts DOWN to encourage selling
    # r = 100 - (10 * 0.1 * 1.0) = 99.0
    # delta remains 1.39
    # bid = 99 - 0.695 = 98.305, ask = 99 + 0.695 = 99.695
    assert quotes[1]["bid_quote"].item() == pytest.approx(98.305, rel=1e-3)
    assert quotes[1]["ask_quote"].item() == pytest.approx(99.695, rel=1e-3)

    # Row 2: Short inventory (-10) -> Reservation price shifts UP to encourage buying
    # r = 100 - (-10 * 0.1 * 1.0) = 101.0
    # bid = 101 - 0.695 = 100.305, ask = 101 + 0.695 = 101.695
    assert quotes[2]["bid_quote"].item() == pytest.approx(100.305, rel=1e-3)
    assert quotes[2]["ask_quote"].item() == pytest.approx(101.695, rel=1e-3)


def test_market_maker_empty_robustness() -> None:
    """Verify behavior with empty input DataFrames."""
    mm = AvellanedaStoikovMarketMaker(gamma=GAMMA, k=K_INTENSITY)
    empty = pl.DataFrame()
    res = mm.compute_quotes(empty)
    assert res.is_empty()
