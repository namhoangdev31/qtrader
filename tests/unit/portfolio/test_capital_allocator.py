import numpy as np
import polars as pl
import pytest

from qtrader.portfolio.allocator import CapitalAllocator


@pytest.fixture
def allocator() -> CapitalAllocator:
    return CapitalAllocator(max_capital_per_strategy=0.50)

@pytest.fixture
def mock_strategy_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    # Strategy A: Steady, Low Vol
    # Strategy B: High Return, High Vol
    # Strategy C: Poor Sharpe, High Vol
    strategy_stats = pl.DataFrame({
        "strategy_id": ["strat_a", "strat_b", "strat_c"],
        "volatility": [0.10, 0.30, 0.40],
        "sharpe": [2.0, 1.5, 0.2],
        "max_drawdown": [0.05, 0.15, 0.25]
    })
    
    # Simple simulated returns for correlation
    strategy_returns = pl.DataFrame({
        "strat_a": [0.01, 0.02, -0.01, 0.015, 0.01],
        "strat_b": [0.03, 0.05, -0.04, 0.06, 0.02],
        "strat_c": [0.01, 0.02, -0.01, 0.015, 0.01]  # High corr with A
    })
    
    return strategy_stats, strategy_returns

def test_risk_parity_allocation(allocator, mock_strategy_data):
    strategy_stats, _ = mock_strategy_data
    # Use only first 2 for pure parity check
    stats_2 = strategy_stats.head(2)
    weights = allocator.allocate(stats_2)
    
    # A has 1/0.1=10, B has 1/0.3=3.33
    # A should have more weight than B
    assert weights["strat_a"] > weights["strat_b"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6

def test_performance_penalties(allocator, mock_strategy_data):
    strategy_stats, _ = mock_strategy_data
    # Set vols equal to isolate performance
    stats_equal_vol = strategy_stats.with_columns(pl.lit(0.2).alias("volatility"))
    weights = allocator.allocate(stats_equal_vol)
    
    # A has highest Sharpe, C has lowest
    assert weights["strat_a"] > weights["strat_b"]
    assert weights["strat_b"] > weights["strat_c"]

def test_max_weight_constraint(allocator, mock_strategy_data):
    strategy_stats, _ = mock_strategy_data
    # Make A extremely good to trigger the cap (0.50)
    stats_extreme = strategy_stats.with_columns([
        pl.when(pl.col("strategy_id") == "strat_a")
        .then(0.01)
        .otherwise(pl.col("volatility"))
        .alias("volatility"),
        pl.when(pl.col("strategy_id") == "strat_a")
        .then(5.0)
        .otherwise(pl.col("sharpe"))
        .alias("sharpe"),
    ])
    
    weights = allocator.allocate(stats_extreme)
    assert weights["strat_a"] <= 0.50 + 1e-6
    assert abs(sum(weights.values()) - 1.0) < 1e-6

def test_correlation_penalty(allocator, mock_strategy_data):
    strategy_stats, strategy_returns = mock_strategy_data
    # A and C are perfectly correlated in mock data (1.0)
    # B is uncorrelated
    weights = allocator.allocate(strategy_stats, strategy_returns)
    
    # Strategy B should be favored more than if it were correlated
    assert weights["strat_b"] > 0
    assert abs(sum(weights.values()) - 1.0) < 1e-6

def test_empty_input(allocator):
    assert allocator.allocate(pl.DataFrame()) == {}
