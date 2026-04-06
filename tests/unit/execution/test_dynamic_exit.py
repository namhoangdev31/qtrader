import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from qtrader.execution.paper_engine import PaperTradingEngine

@pytest.fixture
def engine():
    return PaperTradingEngine(tick_interval=0.1)

@pytest.mark.asyncio
async def test_dynamic_exit_buy_to_sell(engine):
    # 1. Setup price history to allow signal generation
    engine._price_history = [50000.0] * 25
    
    # 2. Open a BUY position manually
    engine._open_managed_position("BUY", 0.5)
    assert "BTC-USD" in engine._managed_positions
    assert engine._managed_positions["BTC-USD"].side == "BUY"
    
    # 3. Simulate a SELL signal with high strength
    # We mock _generate_signal to return a SELL signal
    with patch.object(engine, '_generate_signal', return_value={"action": "SELL", "strength": 0.8}):
        # Run one loop iteration logic
        signal = engine._generate_signal()
        exit_trade = engine._check_dynamic_exit(signal)
        
        assert exit_trade is not None
        assert exit_trade.reason == "DYNAMIC_EXIT"
        assert "BTC-USD" not in engine._managed_positions

@pytest.mark.asyncio
async def test_dynamic_exit_sell_to_buy(engine):
    # 1. Setup price history
    engine._price_history = [50000.0] * 25
    
    # 2. Open a SELL position
    engine._open_managed_position("SELL", 0.5)
    assert engine._managed_positions["BTC-USD"].side == "SELL"
    
    # 3. Simulate a BUY signal
    with patch.object(engine, '_generate_signal', return_value={"action": "BUY", "strength": 0.8}):
        signal = engine._generate_signal()
        exit_trade = engine._check_dynamic_exit(signal)
        
        assert exit_trade is not None
        assert exit_trade.reason == "DYNAMIC_EXIT"
        assert "BTC-USD" not in engine._managed_positions

@pytest.mark.asyncio
async def test_no_dynamic_exit_on_same_signal(engine):
    # 1. Setup
    engine._price_history = [50000.0] * 25
    engine._open_managed_position("BUY", 0.5)
    
    # 2. Simulate another BUY signal (should NOT exit)
    with patch.object(engine, '_generate_signal', return_value={"action": "BUY", "strength": 0.8}):
        signal = engine._generate_signal()
        exit_trade = engine._check_dynamic_exit(signal)
        
        assert exit_trade is None
        assert "BTC-USD" in engine._managed_positions
