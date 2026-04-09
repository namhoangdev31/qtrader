from unittest.mock import MagicMock

import pytest

from qtrader.execution.routing.cost_model import RoutingCostModel


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with cost modeling parameters."""
    cfg = MagicMock()
    # Configuration paths for objective and exchanges
    cfg.objective = {"impact_k": 0.1, "base_fee": 0.0001}
    # Exchange-specific fee structures
    cfg.exchanges = {
        "Binance": {"fees": {"maker": 0.0001, "taker": 0.0005}},
        "Coinbase": {"fees": {"maker": 0.0, "taker": 0.001}},
        "Kraken": {},  # No specific fees (should fallback to base)
    }
    return cfg


def test_routing_cost_fee_sensitivity(execution_config: MagicMock) -> None:
    """Verify that lower fees result in lower total cost when other factors are equal."""
    model = RoutingCostModel(execution_config)

    # 2 venues: Identical price, spread, and liquidity.
    # Binance (0.05% taker) vs Kraken (Baseline 0.01% taker)
    # Kraken should be cheaper for MARKET orders.
    market_data = {
        "Binance": {"asks": [[100.0, 1000.0]], "spread": 0.01},
        "Kraken": {"asks": [[100.0, 1000.0]], "spread": 0.01},
    }

    costs = model.estimate_costs(order_size=10.0, market_data=market_data, order_type="MARKET")

    assert costs["Kraken"] < costs["Binance"]


def test_routing_cost_slippage_dominance(execution_config: MagicMock) -> None:
    """Verify that liquidity becomes the dominant cost factor for large orders."""
    model = RoutingCostModel(execution_config)

    # Binance: Tighter spread (0.01) but Low Liquidity (10.0)
    # Coinbase: Wider spread (0.05) but High Liquidity (1000.0)
    # For a LARGE order (e.g. 50), slippage on Binance will dominate.
    market_data = {
        "Binance": {"asks": [[100.0, 10.0]], "spread": 0.01},
        "Coinbase": {"asks": [[100.0, 1000.0]], "spread": 0.05},
    }

    # Large order (100) -> Market impact cost will spike on Binance
    costs = model.estimate_costs(order_size=100.0, market_data=market_data, order_type="MARKET")

    assert costs["Coinbase"] < costs["Binance"]


def test_routing_cost_spread_sensitivity(execution_config: MagicMock) -> None:
    """Verify that tighter spreads result in lower costs for small orders."""
    model = RoutingCostModel(execution_config)

    # Binance: Tight spread (0.01) vs Coinbase: Wide spread (0.1)
    # Identical fees and high liquidity (no slippage).
    market_data = {
        "Binance": {"asks": [[100.0, 1000.0]], "spread": 0.01},
        "Coinbase": {"asks": [[100.0, 1000.0]], "spread": 0.1},
    }

    # Small order (1.0) -> Spread cost is the primary factor.
    costs = model.estimate_costs(order_size=1.0, market_data=market_data, order_type="MARKET")

    assert costs["Binance"] < costs["Coinbase"]


def test_routing_cost_boundary_conditions(execution_config: MagicMock) -> None:
    """Verify safety logic for zero-size, missing venues, and malformed snapshots."""
    model = RoutingCostModel(execution_config)

    # 1. Zero size
    assert model.estimate_costs(0.0, {"B": {"asks": [[1.0, 1.0]]}}) == {}

    # 2. Empty market data
    assert model.estimate_costs(100.0, {}) == {}

    # 3. Malformed snapshots (Missing asks/bids)
    market_data = {"NULL": {}}  # No price/liquidity data
    costs = model.estimate_costs(10.0, market_data)
    # Should fallback gracefully (price=1.0, liq=1.0)
    assert costs["NULL"] > 0.0


def test_routing_cost_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify that the model handles malformed data silently with a penalty."""
    model = RoutingCostModel(execution_config)

    # Passing a non-dict to trigger Exception in _calculate_venue_cost
    market_data = {"V1": "STALE_DATA"}  # type: ignore
    costs = model.estimate_costs(10.0, market_data)

    # Should return failsafe penalty (1e18)
    assert costs["V1"] == 1e18
