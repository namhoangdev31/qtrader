from unittest.mock import MagicMock

import pytest

from qtrader.execution.routing.fill_model import VenueFillProbabilityModel


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with probability baseline parameters."""
    cfg = MagicMock()
    # Configuration paths for objective and exchanges
    cfg.microstructure = {"queue_model": {"default_intensity": 10.0}}
    return cfg


def test_venue_fill_probability_latency_sensitivity(execution_config: MagicMock) -> None:
    """Verify that venues with higher latency receive lower fill probabilities."""
    model = VenueFillProbabilityModel(execution_config)
    
    # 2 venues: Identical intensity (10) and queue (50).
    # Binance (5ms latency) vs Coinbase (50ms latency)
    # Horizon: 60ms (0.06s)
    market_stats = {
        "Binance": {"intensity": 10.0, "liquidity": 50.0},
        "Coinbase": {"intensity": 10.0, "liquidity": 50.0}
    }
    latencies = {
        "Binance": 0.005,  # 5ms
        "Coinbase": 0.050  # 50ms
    }
    
    probs = model.estimate_fill_probabilities(
        time_horizon=0.060, market_stats=market_stats, latencies=latencies
    )
    
    # Binance should have a higher probability due to lower latency drift
    assert probs["Binance"] > probs["Coinbase"]
    assert probs["Binance"] > 0.0


def test_venue_fill_probability_latency_cutoff(execution_config: MagicMock) -> None:
    """Verify that fill probability is zero if latency exceeds the time horizon."""
    model = VenueFillProbabilityModel(execution_config)
    
    # Horizon: 10ms (0.010s)
    # Venue: 50ms latency -> Impossible to fill
    market_stats = {"V1": {"intensity": 100.0, "liquidity": 1.0}}
    latencies = {"V1": 0.050}
    
    probs = model.estimate_fill_probabilities(
        time_horizon=0.010, market_stats=market_stats, latencies=latencies
    )
    
    assert probs["V1"] == 0.0


def test_venue_fill_probability_intensity_dominance(execution_config: MagicMock) -> None:
    """Verify that high trade intensity can compensate for moderate latency."""
    model = VenueFillProbabilityModel(execution_config)
    
    # Low-LTC (5ms) but Low-Intensity (1)
    # High-LTC (20ms) but High-Intensity (50)
    market_stats = {
        "Binance": {"intensity": 1.0, "liquidity": 100.0},
        "Coinbase": {"intensity": 50.0, "liquidity": 100.0}
    }
    latencies = {
        "Binance": 0.005,
        "Coinbase": 0.020
    }
    
    # Horizon: 100ms (0.1s)
    probs = model.estimate_fill_probabilities(
        time_horizon=0.1, market_stats=market_stats, latencies=latencies
    )
    
    # High intensity on Coinbase should overcome the 15ms latency handicap
    assert probs["Coinbase"] > probs["Binance"]


def test_venue_fill_probability_boundary_conditions(execution_config: MagicMock) -> None:
    """Verify safety logic for zero-horizon and missing venue data."""
    model = VenueFillProbabilityModel(execution_config)
    
    # 1. Zero horizon
    assert model.estimate_fill_probabilities(0.0, {"B": {}}, {}) == {"B": 0.0}
    
    # 2. Empty market data
    assert model.estimate_fill_probabilities(1.0, {}, {}) == {}
    
    # 3. Missing latencies (should fallback to zero)
    market_stats = {"V1": {"intensity": 10.0, "liquidity": 100.0}}
    probs = model.estimate_fill_probabilities(
        time_horizon=1.0, market_stats=market_stats, latencies={}
    )
    assert probs["V1"] > 0.0
