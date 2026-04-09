from unittest.mock import MagicMock
import pytest
from qtrader.execution.routing.cost_model import RoutingCostModel


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.objective = {"impact_k": 0.1, "base_fee": 0.0001}
    cfg.exchanges = {
        "Binance": {"fees": {"maker": 0.0001, "taker": 0.0005}},
        "Coinbase": {"fees": {"maker": 0.0, "taker": 0.001}},
        "Kraken": {},
    }
    return cfg


def test_routing_cost_fee_sensitivity(execution_config: MagicMock) -> None:
    model = RoutingCostModel(execution_config)
    market_data = {
        "Binance": {"asks": [[100.0, 1000.0]], "spread": 0.01},
        "Kraken": {"asks": [[100.0, 1000.0]], "spread": 0.01},
    }
    costs = model.estimate_costs(order_size=10.0, market_data=market_data, order_type="MARKET")
    assert costs["Kraken"] < costs["Binance"]


def test_routing_cost_slippage_dominance(execution_config: MagicMock) -> None:
    model = RoutingCostModel(execution_config)
    market_data = {
        "Binance": {"asks": [[100.0, 10.0]], "spread": 0.01},
        "Coinbase": {"asks": [[100.0, 1000.0]], "spread": 0.05},
    }
    costs = model.estimate_costs(order_size=100.0, market_data=market_data, order_type="MARKET")
    assert costs["Coinbase"] < costs["Binance"]


def test_routing_cost_spread_sensitivity(execution_config: MagicMock) -> None:
    model = RoutingCostModel(execution_config)
    market_data = {
        "Binance": {"asks": [[100.0, 1000.0]], "spread": 0.01},
        "Coinbase": {"asks": [[100.0, 1000.0]], "spread": 0.1},
    }
    costs = model.estimate_costs(order_size=1.0, market_data=market_data, order_type="MARKET")
    assert costs["Binance"] < costs["Coinbase"]


def test_routing_cost_boundary_conditions(execution_config: MagicMock) -> None:
    model = RoutingCostModel(execution_config)
    assert model.estimate_costs(0.0, {"B": {"asks": [[1.0, 1.0]]}}) == {}
    assert model.estimate_costs(100.0, {}) == {}
    market_data = {"NULL": {}}
    costs = model.estimate_costs(10.0, market_data)
    assert costs["NULL"] > 0.0


def test_routing_cost_catastrophic_safety(execution_config: MagicMock) -> None:
    model = RoutingCostModel(execution_config)
    market_data = {"V1": "STALE_DATA"}
    costs = model.estimate_costs(10.0, market_data)
    assert costs["V1"] == 1e18
