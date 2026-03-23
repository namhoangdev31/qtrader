import pytest
from qtrader.risk.runtime_risk_engine import RuntimeRiskEngine
from qtrader.core.types import Order, Side

def test_risk_engine_initialization():
    engine = RuntimeRiskEngine(max_drawdown=0.1, max_position_size=1000.0)
    assert engine.max_drawdown == 0.1
    assert engine.max_position_size == 1000.0

def test_risk_engine_check_order_allowed():
    engine = RuntimeRiskEngine(max_position_size=2000.0)
    mock_order = Order(symbol="BTC", side=Side.Buy, quantity=1.0, price=1000.0)
    mock_account = MagicMock()
    mock_account.get_position.return_value = 0.0
    
    is_allowed, reason = engine.check_order(mock_order, mock_account)
    assert is_allowed is True
    assert reason == ""

def test_risk_engine_check_order_exceeds_size():
    engine = RuntimeRiskEngine(max_position_size=500.0)
    mock_order = Order(symbol="BTC", side=Side.Buy, quantity=1.0, price=1000.0)
    mock_account = MagicMock()
    mock_account.get_position.return_value = 0.0
    
    is_allowed, reason = engine.check_order(mock_order, mock_account)
    assert is_allowed is False
    assert "exceeds maximum position size" in reason.lower()

def test_risk_engine_check_drawdown_limit():
    engine = RuntimeRiskEngine(max_drawdown=0.05)
    mock_account = MagicMock()
    mock_account.get_drawdown.return_value = 0.06
    
    assert engine.is_trading_allowed(mock_account) is False
