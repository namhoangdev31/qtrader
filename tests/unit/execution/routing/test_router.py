from unittest.mock import MagicMock
import pytest
from qtrader.execution.routing.router import DynamicRoutingEngine


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.microstructure = {"queue_model": {"default_intensity": 10.0}}
    cfg.objective = {"impact_k": 0.1, "base_fee": 0.0001}
    cfg.exchanges = {
        "Binance": {"fees": {"maker": 0.0001, "taker": 0.0005}},
        "Coinbase": {"fees": {"maker": 0.001, "taker": 0.005}},
    }
    return cfg


def test_dynamic_router_selection_accuracy(execution_config: MagicMock) -> None:
    engine = DynamicRoutingEngine(execution_config)
    market_data = {
        "Binance": {"asks": [[100.0, 1000.0]], "intensity": 50.0},
        "Coinbase": {"asks": [[100.0, 10.0]], "intensity": 1.0},
    }
    latencies = {"Binance": 0.005, "Coinbase": 0.05}
    allocation = engine.route(
        order_size=10.0, side="BUY", market_data=market_data, latencies=latencies
    )
    assert "Binance" in allocation
    assert allocation["Binance"] > 9.9


def test_dynamic_router_splitting_logic(execution_config: MagicMock) -> None:
    engine = DynamicRoutingEngine(execution_config)
    market_data = {
        "V1": {"asks": [[100.0, 500.0]], "intensity": 10.0},
        "V2": {"asks": [[100.0, 500.0]], "intensity": 10.0},
    }
    latencies = {"V1": 0.01, "V2": 0.01}
    allocation = engine.route(
        order_size=100.0, side="BUY", market_data=market_data, latencies=latencies
    )
    assert "V1" in allocation
    assert "V2" in allocation
    assert allocation["V1"] == pytest.approx(50.0)
    assert allocation["V2"] == pytest.approx(50.0)


def test_dynamic_router_failsafe_recovery(execution_config: MagicMock) -> None:
    engine = DynamicRoutingEngine(execution_config)
    market_data = {"Binance": {"asks": [[100.0, 10.0]]}, "Coinbase": {"asks": [[100.0, 100.0]]}}
    latencies = {"Binance": 0.0, "Coinbase": 0.0}
    allocation = engine.route(
        order_size=10.0, side="BUY", market_data=market_data, latencies=latencies, time_horizon=0.0
    )
    assert allocation["Coinbase"] == 10.0


def test_dynamic_router_penalty_resilience(execution_config: MagicMock) -> None:
    engine = DynamicRoutingEngine(execution_config)
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
    engine = DynamicRoutingEngine(execution_config)
    assert engine.route(10.0, "BUY", {}, {}) == {}
