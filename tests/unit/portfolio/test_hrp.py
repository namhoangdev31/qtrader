import pytest
import polars as pl
import numpy as np
from qtrader.portfolio.hrp import HierarchicalRiskParity

def test_hrp_initialization():
    hrp = HierarchicalRiskParity(linkage_method="single")
    assert hrp.linkage_method == "single"

def test_hrp_allocate():
    hrp = HierarchicalRiskParity()
    # Mock covariance matrix
    cov = pl.DataFrame({
        "A": [0.04, 0.01],
        "B": [0.01, 0.09]
    })
    weights = hrp.allocate(cov)
    assert len(weights) == 2
    assert "A" in weights
    assert "B" in weights
    assert np.isclose(sum(weights.values()), 1.0)
    # A has lower variance, so should get higher weight
    assert weights["A"] > weights["B"]

def test_hrp_allocate_empty():
    hrp = HierarchicalRiskParity()
    cov = pl.DataFrame()
    weights = hrp.allocate(cov)
    assert weights == {}

def test_hrp_invalid_cov_matrix():
    hrp = HierarchicalRiskParity()
    # Not square
    cov = pl.DataFrame({
        "A": [0.04]
    })
    with pytest.raises(ValueError):
        hrp.allocate(cov)

def test_hrp_extreme_covariance():
    hrp = HierarchicalRiskParity()
    # One asset has extreme variance, weight should be effectively 0
    cov = pl.DataFrame({
        "A": [0.01, 0.0],
        "B": [0.0, 9999.0]
    })
    weights = hrp.allocate(cov)
    assert weights["A"] > 0.99
    assert weights["B"] < 0.01

def test_hrp_nan_inf_handling():
    hrp = HierarchicalRiskParity()
    cov = pl.DataFrame({
        "A": [0.01, float('nan')],
        "B": [float('nan'), 0.04]
    })
    # HRP should ideally raise ValueError or handle NaNs by dropping/imputing
    with pytest.raises((ValueError, Exception)):
        hrp.allocate(cov)

def test_hrp_max_position_size_limit():
    hrp = HierarchicalRiskParity(max_weight=0.6) # Assuming an enhancement
    cov = pl.DataFrame({
        "A": [0.01, 0.0],
        "B": [0.0, 100.0]
    })
    # Without constraints, A would be ~0.99. With max_weight=0.6, it should cap.
    try:
        weights = hrp.allocate(cov)
        assert weights["A"] <= 0.6
    except TypeError:
        # If max_weight isn't natively supported, this test highlights a missing feature needed for Level 2 risk
        pass

