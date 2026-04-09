from unittest.mock import MagicMock
import pytest
from qtrader.execution.routing.fill_model import VenueFillProbabilityModel


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.microstructure = {"queue_model": {"default_intensity": 10.0}}
    return cfg


def test_venue_fill_probability_latency_sensitivity(execution_config: MagicMock) -> None:
    model = VenueFillProbabilityModel(execution_config)
    market_stats = {
        "Binance": {"intensity": 10.0, "liquidity": 50.0},
        "Coinbase": {"intensity": 10.0, "liquidity": 50.0},
    }
    latencies = {"Binance": 0.005, "Coinbase": 0.05}
    probs = model.estimate_fill_probabilities(
        time_horizon=0.06, market_stats=market_stats, latencies=latencies
    )
    assert probs["Binance"] > probs["Coinbase"]
    assert probs["Binance"] > 0.0


def test_venue_fill_probability_latency_cutoff(execution_config: MagicMock) -> None:
    model = VenueFillProbabilityModel(execution_config)
    market_stats = {"V1": {"intensity": 100.0, "liquidity": 1.0}}
    latencies = {"V1": 0.05}
    probs = model.estimate_fill_probabilities(
        time_horizon=0.01, market_stats=market_stats, latencies=latencies
    )
    assert probs["V1"] == 0.0


def test_venue_fill_probability_intensity_dominance(execution_config: MagicMock) -> None:
    model = VenueFillProbabilityModel(execution_config)
    market_stats = {
        "Binance": {"intensity": 1.0, "liquidity": 100.0},
        "Coinbase": {"intensity": 50.0, "liquidity": 100.0},
    }
    latencies = {"Binance": 0.005, "Coinbase": 0.02}
    probs = model.estimate_fill_probabilities(
        time_horizon=0.1, market_stats=market_stats, latencies=latencies
    )
    assert probs["Coinbase"] > probs["Binance"]


def test_venue_fill_probability_boundary_conditions(execution_config: MagicMock) -> None:
    model = VenueFillProbabilityModel(execution_config)
    assert model.estimate_fill_probabilities(0.0, {"B": {}}, {}) == {"B": 0.0}
    assert model.estimate_fill_probabilities(1.0, {}, {}) == {}
    market_stats = {"V1": {"intensity": 10.0, "liquidity": 100.0}}
    probs = model.estimate_fill_probabilities(
        time_horizon=1.0, market_stats=market_stats, latencies={}
    )
    assert probs["V1"] > 0.0
