import pytest
import numpy as np
import polars as pl
from qtrader.risk.factor_risk import FactorRiskEngine

@pytest.fixture
def engine() -> FactorRiskEngine:
    return FactorRiskEngine()

@pytest.fixture
def mock_data() -> tuple:
    positions = {"BTC": 1.0, "ETH": 10.0}
    prices = {"BTC": 60000.0, "ETH": 3000.0}
    
    # Factor Exposures: Symbol, Market, Beta, Style
    exposures = pl.DataFrame({
        "symbol": ["BTC", "ETH"],
        "market": [1.2, 0.8],
        "growth": [0.5, 0.9]
    })
    
    # Factor Covariance (Market, Growth)
    covariance = pl.DataFrame({
        "market": [0.0004, 0.0002],  # 2% vol, 0.5 correlation
        "growth": [0.0002, 0.0009]   # 3% vol
    })
    
    idiosyncratic_vols = {"BTC": 0.05, "ETH": 0.08}
    
    return positions, prices, exposures, covariance, idiosyncratic_vols

def test_factor_risk_decomposition(engine, mock_data):
    positions, prices, exposures, covariance, idiosyncratic_vols = mock_data
    
    result = engine.decompose_risk(
        positions, prices, exposures, covariance, idiosyncratic_vols
    )
    
    assert "total_risk" in result
    assert "factor_contributions" in result
    assert "marginal_vars" in result
    
    total_vol = result["total_risk"]
    assert total_vol > 0
    
    # Check that factor contributions exist for all factors
    assert "market" in result["factor_contributions"]
    assert "growth" in result["factor_contributions"]
    
    # Systematic + Specific should equal total (in variance terms)
    # var = vol^2
    var_calculated = result["systematic_risk"]**2 + result["specific_risk"]**2
    assert abs(var_calculated - total_vol**2) < 1e-10

def test_factor_risk_empty_portfolio(engine):
    result = engine.decompose_risk({}, {}, pl.DataFrame(), pl.DataFrame())
    assert result["total_risk"] == 0.0
    assert result["factor_contributions"] == {}

def test_concentration_detection(engine):
    # Dummy result where 'market' has high contribution
    decomposition = {
        "total_risk": 0.1,
        "factor_contributions": {"market": 0.05, "style": 0.001}
        # 0.05 / 0.1 = 50% > 40% threshold
    }
    
    warnings = engine.detect_concentration(decomposition, threshold=0.40)
    assert len(warnings) == 1
    assert "market" in warnings[0]
