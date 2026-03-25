from unittest.mock import MagicMock
import polars as pl
from datetime import datetime
from qtrader.risk.runtime_risk_engine import AdvancedRiskEngine
from qtrader.core.types import Side

def test_risk_engine_initialization():
    engine = AdvancedRiskEngine(max_drawdown_threshold=0.1, max_position_size=0.1)
    assert engine.max_drawdown_threshold == 0.1
    assert engine.max_position_size == 0.1

def test_risk_engine_compute_risk_allowed():
    engine = AdvancedRiskEngine(max_position_size=0.2)
    positions = {"CASH": 10000.0}
    prices = {"BTC": 1000.0, "CASH": 1.0}
    proposed_trade = {"symbol": "BTC", "quantity": 0.1, "side": "buy"}
    # Need some historical returns for VaR and other metrics
    hist_returns = pl.DataFrame({
        "BTC": [0.01, -0.01, 0.02, 0.01, -0.01],
        "CASH": [0.0, 0.0, 0.0, 0.0, 0.0]
    })
    
    result = engine.compute_risk(positions, prices, proposed_trade, hist_returns)
    print(f"DEBUG: Result: {result}")
    assert result["approved"] is True, f"Risk engine rejected: {result.get('reason')}"
    assert "Within risk limits" in result["reason"]

def test_risk_engine_compute_risk_exceeds_size():
    engine = AdvancedRiskEngine(max_position_size=0.05)
    positions = {"CASH": 1000.0} # Lower cash to make trade size impact larger relative to portfolio
    prices = {"BTC": 100.0, "CASH": 1.0}
    # Trade value = 50 * 100 = 5000. Total value = 5000 + 1000 = 6000. 5000/6000 = 83% > 5%
    proposed_trade = {"symbol": "BTC", "quantity": 50.0, "side": "buy"}
    hist_returns = pl.DataFrame({
        "BTC": [0.01] * 10,
        "CASH": [0.0] * 10
    })
    
    result = engine.compute_risk(positions, prices, proposed_trade, hist_returns)
    if result["approved"]:
        assert result["adjusted_size"] < 50.0
        assert "Position size exceeds" in result["reason"]
