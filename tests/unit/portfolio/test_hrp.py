import numpy as np
import polars as pl
import pytest

from qtrader.portfolio.hrp import HRPOptimizer


def test_hrp_initialization():
    hrp = HRPOptimizer()
    # No linkage_method in __init__ for this version
    assert hasattr(hrp, 'optimize')

def test_hrp_optimize():
    hrp = HRPOptimizer()
    # Mock returns DataFrame with 3 assets to ensure hierarchy works reliably
    returns = pl.DataFrame({
        "A": np.random.normal(0.001, 0.02, 100),
        "B": np.random.normal(0.001, 0.04, 100),
        "C": np.random.normal(0.001, 0.06, 100)
    })
    weights = hrp.optimize(returns)
    assert len(weights) == 3
    assert "A" in weights
    assert "B" in weights
    assert "C" in weights
    assert np.isclose(sum(weights.values()), 1.0)
    # A has lowest variance, so should get higher weight than B and C
    assert weights["A"] > weights["B"]
    assert weights["B"] > weights["C"]

def test_hrp_optimize_empty():
    hrp = HRPOptimizer()
    returns = pl.DataFrame()
    weights = hrp.optimize(returns)
    assert weights == {}

def test_hrp_nan_inf_handling():
    hrp = HRPOptimizer()
    returns = pl.DataFrame({
        "A": [0.01, float('nan'), 0.03],
        "B": [0.02, 0.02, 0.04]
    })
    # Most ML/Stats models will fail on NaNs without preprocessing
    with pytest.raises(Exception):
        hrp.optimize(returns)

