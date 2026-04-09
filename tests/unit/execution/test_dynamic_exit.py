from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from qtrader.execution.paper_engine import PaperTradingEngine


@pytest.fixture
def engine():
    return PaperTradingEngine(tick_interval=0.1)


@pytest.mark.asyncio
async def test_dynamic_exit_buy_to_sell(engine):
    engine._price_history = [50000.0] * 25
    engine._open_managed_position("BUY", 0.5)
    assert "BTC-USD" in engine._managed_positions
    assert engine._managed_positions["BTC-USD"][0].side == "BUY"
    with patch.object(engine, "_generate_signal", return_value={"action": "SELL", "strength": 0.8}):
        signal = engine._generate_signal()
        exit_trade = engine._check_dynamic_exit(signal)
        assert exit_trade is not None
        assert exit_trade.reason == "DYNAMIC_EXIT"
        assert "BTC-USD" not in engine._managed_positions


@pytest.mark.asyncio
async def test_dynamic_exit_sell_to_buy(engine):
    engine._price_history = [50000.0] * 25
    engine._open_managed_position("SELL", 0.5)
    assert engine._managed_positions["BTC-USD"][0].side == "SELL"
    with patch.object(engine, "_generate_signal", return_value={"action": "BUY", "strength": 0.8}):
        signal = engine._generate_signal()
        exit_trade = engine._check_dynamic_exit(signal)
        assert exit_trade is not None
        assert exit_trade.reason == "DYNAMIC_EXIT"
        assert "BTC-USD" not in engine._managed_positions


@pytest.mark.asyncio
async def test_no_dynamic_exit_on_same_signal(engine):
    engine._price_history = [50000.0] * 25
    engine._open_managed_position("BUY", 0.5)
    with patch.object(engine, "_generate_signal", return_value={"action": "BUY", "strength": 0.8}):
        signal = engine._generate_signal()
        exit_trade = engine._check_dynamic_exit(signal)
        assert exit_trade is None
        assert "BTC-USD" in engine._managed_positions
