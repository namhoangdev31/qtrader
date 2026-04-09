import pytest
from qtrader.execution.routing.liquidity_model import MultiVenueLiquidityModel


def test_liquidity_model_depth_sensitivity() -> None:
    model = MultiVenueLiquidityModel(n_levels=3)
    market_data = {
        "Binance": {"asks": [[100.0, 100.0], [100.1, 10.0], [100.2, 10.0]]},
        "Coinbase": {"asks": [[100.0, 10.0], [100.1, 10.0], [100.2, 100.0]]},
    }
    scores = model.compute_scores(market_data, side="BUY")
    assert scores["Binance"] > scores["Coinbase"]
    assert pytest.approx(sum(scores.values())) == 1.0


def test_liquidity_model_normalization_integrity() -> None:
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
    model = MultiVenueLiquidityModel(n_levels=1)
    market_data = {
        "V1": {"asks": [[100.0, 100.0]], "bids": [[99.0, 1.0]]},
        "V2": {"asks": [[100.0, 1.0]], "bids": [[99.0, 100.0]]},
    }
    buy_scores = model.compute_scores(market_data, side="BUY")
    sell_scores = model.compute_scores(market_data, side="SELL")
    assert buy_scores["V1"] > buy_scores["V2"]
    assert sell_scores["V2"] > sell_scores["V1"]


def test_liquidity_model_stale_data_resilience() -> None:
    model = MultiVenueLiquidityModel(n_levels=5)
    market_data = {"Binance": {"asks": [[100.0, 100.0]]}, "Coinbase": {"asks": []}, "Kraken": {}}
    scores = model.compute_scores(market_data, side="BUY")
    assert scores["Binance"] == pytest.approx(1.0)
    assert scores["Coinbase"] == 0.0
    assert scores["Kraken"] == 0.0


def test_liquidity_model_failsafe_distribution() -> None:
    model = MultiVenueLiquidityModel(n_levels=5)
    market_data = {"V1": {"asks": []}, "V2": {"asks": []}}
    scores = model.compute_scores(market_data, side="BUY")
    assert scores["V1"] == pytest.approx(0.5)
    assert scores["V2"] == pytest.approx(0.5)


def test_liquidity_model_empty_market_data() -> None:
    model = MultiVenueLiquidityModel()
    assert model.compute_scores({}) == {}


def test_liquidity_model_malformed_levels() -> None:
    model = MultiVenueLiquidityModel()
    market_data = {"V1": {"asks": [[100.0]]}}
    scores = model.compute_scores(market_data)
    assert scores["V1"] == 1.0


def test_liquidity_model_exception_handling() -> None:
    model = MultiVenueLiquidityModel()
    market_data = {"V1": "NOT_A_DICT"}
    scores = model.compute_scores(market_data)
    assert scores["V1"] == 1.0
