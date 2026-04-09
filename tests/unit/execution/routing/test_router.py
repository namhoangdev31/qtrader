from unittest.mock import MagicMock

import pytest

from qtrader.execution.routing.router import DynamicRoutingEngine


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with probability baseline parameters."""
    cfg = MagicMock()
    # Configuration paths for objective and exchanges
    cfg.microstructure = {"queue_model": {"default_intensity": 10.0}}
    cfg.objective = {"impact_k": 0.1, "base_fee": 0.0001}
    cfg.exchanges = {
        "Binance": {"fees": {"maker": 0.0001, "taker": 0.0005}},
        "Coinbase": {"fees": {"maker": 0.001, "taker": 0.005}},
    }
    return cfg


def test_dynamic_router_selection_accuracy(execution_config: MagicMock) -> None:
    """Verify that the engine selects the venue with the highest normalized score."""
    engine = DynamicRoutingEngine(execution_config)

    # Binance: High liquidity (1000), Low Fee (0.0005), Low Latency (5ms)
    # Coinbase: Low liquidity (10), High Fee (0.005), High Latency (50ms)
    market_data = {
        "Binance": {"asks": [[100.0, 1000.0]], "intensity": 50.0},
        "Coinbase": {"asks": [[100.0, 10.0]], "intensity": 1.0},
    }
    latencies = {"Binance": 0.005, "Coinbase": 0.050}

    allocation = engine.route(
        order_size=10.0, side="BUY", market_data=market_data, latencies=latencies
    )

    # Binance should receive nearly 100% of the order
    assert "Binance" in allocation
    assert allocation["Binance"] > 9.9


def test_dynamic_router_splitting_logic(execution_config: MagicMock) -> None:
    """Verify that volume is split across venues when scores are comparable."""
    engine = DynamicRoutingEngine(execution_config)

    # Two identical venues: Should split 1:1
    market_data = {
        "V1": {"asks": [[100.0, 500.0]], "intensity": 10.0},
        "V2": {"asks": [[100.0, 500.0]], "intensity": 10.0},
    }
    latencies = {"V1": 0.010, "V2": 0.010}

    allocation = engine.route(
        order_size=100.0, side="BUY", market_data=market_data, latencies=latencies
    )

    assert "V1" in allocation
    assert "V2" in allocation
    assert allocation["V1"] == pytest.approx(50.0)
    assert allocation["V2"] == pytest.approx(50.0)


def test_dynamic_router_failsafe_recovery(execution_config: MagicMock) -> None:
    """Verify that the router falls back to best liquidity when all scores are zero."""
    engine = DynamicRoutingEngine(execution_config)

    # All venues have zero horizon -> zero fill probability -> zero score
    market_data = {
        "Binance": {"asks": [[100.0, 10.0]]},
        "Coinbase": {"asks": [[100.0, 100.0]]},  # Best liquidity
    }
    latencies = {"Binance": 0.0, "Coinbase": 0.0}

    # Set time_horizon to 0 to force zero scores
    allocation = engine.route(
        order_size=10.0, side="BUY", market_data=market_data, latencies=latencies, time_horizon=0.0
    )

    # Should fallback to the venue with best liquidity (Coinbase)
    assert allocation["Coinbase"] == 10.0


def test_dynamic_router_penalty_resilience(execution_config: MagicMock) -> None:
    """Verify that the router avoids high-cost or zero-liquidity venues."""
    engine = DynamicRoutingEngine(execution_config)

    # Binance: Normal
    # Coinbase: Stale/Zero Liquidity
    market_data = {
        "Binance": {"asks": [[100.0, 100.0]], "intensity": 10.0},
        "Coinbase": {"asks": []},
    }
    latencies = {"Binance": 0.005, "Coinbase": 0.005}

    allocation = engine.route(
        order_size=10.0, side="BUY", market_data=market_data, latencies=latencies
    )

    assert "Coinbase" not in allocation
    assert allocation["Binance"] == 10.0


def test_dynamic_router_empty_market_data(execution_config: MagicMock) -> None:
    """Verify behavior with completely empty market inputs."""
    engine = DynamicRoutingEngine(execution_config)
    assert engine.route(10.0, "BUY", {}, {}) == {}
