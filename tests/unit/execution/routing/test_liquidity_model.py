import pytest

from qtrader.execution.routing.liquidity_model import MultiVenueLiquidityModel


def test_liquidity_model_depth_sensitivity() -> None:
    """Verify that venues with more volume at top levels receive higher scores."""
    model = MultiVenueLiquidityModel(n_levels=3)

    # Venue A: High top-of-book volume (100)
    # Venue B: High deeper-book volume (100 at level 3)
    market_data = {
        "Binance": {"asks": [[100.0, 100.0], [100.1, 10.0], [100.2, 10.0]]},
        "Coinbase": {"asks": [[100.0, 10.0], [100.1, 10.0], [100.2, 100.0]]},
    }

    scores = model.compute_scores(market_data, side="BUY")

    # Binance should have a significantly higher score because its top volume has more weight
    assert scores["Binance"] > scores["Coinbase"]
    assert pytest.approx(sum(scores.values())) == 1.0


def test_liquidity_model_normalization_integrity() -> None:
    """Verify that scores across venues sum to 1.0 (relative ranking)."""
    model = MultiVenueLiquidityModel(n_levels=5)

    market_data = {
        "V1": {"asks": [[1.0, 50.0]]},
        "V2": {"asks": [[1.0, 30.0]]},
        "V3": {"asks": [[1.0, 20.0]]},
    }

    scores = model.compute_scores(market_data, side="BUY")

    assert scores["V1"] == pytest.approx(0.5)
    assert scores["V2"] == pytest.approx(0.3)
    assert scores["V3"] == pytest.approx(0.2)
    assert pytest.approx(sum(scores.values())) == 1.0


def test_liquidity_model_side_separation() -> None:
    """Verify that BUY and SELL liquidity are correctly separated."""
    model = MultiVenueLiquidityModel(n_levels=1)

    # V1 is liquid for BUY (asks), V2 is liquid for SELL (bids)
    market_data = {
        "V1": {"asks": [[100.0, 100.0]], "bids": [[99.0, 1.0]]},
        "V2": {"asks": [[100.0, 1.0]], "bids": [[99.0, 100.0]]},
    }

    buy_scores = model.compute_scores(market_data, side="BUY")
    sell_scores = model.compute_scores(market_data, side="SELL")

    assert buy_scores["V1"] > buy_scores["V2"]
    assert sell_scores["V2"] > sell_scores["V1"]


def test_liquidity_model_stale_data_resilience() -> None:
    """Verify that model handles missing or malformed venue data gracefully."""
    model = MultiVenueLiquidityModel(n_levels=5)

    market_data = {
        "Binance": {"asks": [[100.0, 100.0]]},
        "Coinbase": {"asks": []},  # Empty data
        "Kraken": {},  # Stale/Missing data
    }

    scores = model.compute_scores(market_data, side="BUY")

    assert scores["Binance"] == pytest.approx(1.0)
    assert scores["Coinbase"] == 0.0
    assert scores["Kraken"] == 0.0


def test_liquidity_model_failsafe_distribution() -> None:
    """Verify uniform fallback when no liquidity is found anywhere."""
    model = MultiVenueLiquidityModel(n_levels=5)

    market_data = {"V1": {"asks": []}, "V2": {"asks": []}}

    scores = model.compute_scores(market_data, side="BUY")

    assert scores["V1"] == pytest.approx(0.5)
    assert scores["V2"] == pytest.approx(0.5)


def test_liquidity_model_empty_market_data() -> None:
    """Verify behavior with completely empty inputs."""
    model = MultiVenueLiquidityModel()
    assert model.compute_scores({}) == {}


def test_liquidity_model_malformed_levels() -> None:
    """Verify behavior with malformed level data."""
    model = MultiVenueLiquidityModel()
    # Level with only 1 element (missing size)
    market_data = {"V1": {"asks": [[100.0]]}}
    scores = model.compute_scores(market_data)
    assert scores["V1"] == 1.0


def test_liquidity_model_exception_handling() -> None:
    """Verify that the model handles internal exceptions gracefully."""
    model = MultiVenueLiquidityModel()
    # Passing a non-dict to trigger Exception in _calculate_venue_liquidity
    market_data = {"V1": "NOT_A_DICT"}
    scores = model.compute_scores(market_data)  # type: ignore
    assert scores["V1"] == 1.0
