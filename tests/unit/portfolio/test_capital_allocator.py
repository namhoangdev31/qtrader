import numpy as np
import polars as pl
import pytest
from qtrader.portfolio.allocator import CapitalAllocator


@pytest.fixture
def allocator() -> CapitalAllocator:
    return CapitalAllocator(max_capital_per_strategy=0.5)


@pytest.fixture
def mock_strategy_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    strategy_stats = pl.DataFrame(
        {
            "strategy_id": ["strat_a", "strat_b", "strat_c"],
            "volatility": [0.1, 0.3, 0.4],
            "sharpe": [2.0, 1.5, 0.2],
            "max_drawdown": [0.05, 0.15, 0.25],
        }
    )
    strategy_returns = pl.DataFrame(
        {
            "strat_a": [0.01, 0.02, -0.01, 0.015, 0.01],
            "strat_b": [0.03, 0.05, -0.04, 0.06, 0.02],
            "strat_c": [0.01, 0.02, -0.01, 0.015, 0.01],
        }
    )
    return (strategy_stats, strategy_returns)


def test_risk_parity_allocation(allocator, mock_strategy_data):
    (strategy_stats, _) = mock_strategy_data
    stats_2 = strategy_stats.head(2)
    weights = allocator.allocate(stats_2)
    assert weights["strat_a"] > weights["strat_b"]
    assert abs(sum(weights.values()) - 1.0) < 1e-06


def test_performance_penalties(allocator, mock_strategy_data):
    (strategy_stats, _) = mock_strategy_data
    stats_equal_vol = strategy_stats.with_columns(pl.lit(0.2).alias("volatility"))
    weights = allocator.allocate(stats_equal_vol)
    assert weights["strat_a"] > weights["strat_b"]
    assert weights["strat_b"] > weights["strat_c"]


def test_max_weight_constraint(allocator, mock_strategy_data):
    (strategy_stats, _) = mock_strategy_data
    stats_extreme = strategy_stats.with_columns(
        [
            pl.when(pl.col("strategy_id") == "strat_a")
            .then(0.01)
            .otherwise(pl.col("volatility"))
            .alias("volatility"),
            pl.when(pl.col("strategy_id") == "strat_a")
            .then(5.0)
            .otherwise(pl.col("sharpe"))
            .alias("sharpe"),
        ]
    )
    weights = allocator.allocate(stats_extreme)
    assert weights["strat_a"] <= 0.5 + 1e-06
    assert abs(sum(weights.values()) - 1.0) < 1e-06


def test_correlation_penalty(allocator, mock_strategy_data):
    (strategy_stats, strategy_returns) = mock_strategy_data
    weights = allocator.allocate(strategy_stats, strategy_returns)
    assert weights["strat_b"] > 0
    assert abs(sum(weights.values()) - 1.0) < 1e-06


def test_empty_input(allocator):
    assert allocator.allocate(pl.DataFrame()) == {}
