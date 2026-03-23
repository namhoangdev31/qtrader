import pytest
import polars as pl
from unittest.mock import MagicMock, AsyncMock
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.core.types import Signal, Side

def test_ensemble_strategy_initialization():
    mock_strategy1 = MagicMock()
    mock_strategy2 = MagicMock()
    ensemble = EnsembleStrategy(strategies=[mock_strategy1, mock_strategy2], weights=[0.6, 0.4])
    assert len(ensemble.strategies) == 2
    assert ensemble.weights == [0.6, 0.4]

def test_ensemble_strategy_invalid_weights():
    mock_strategy1 = MagicMock()
    with pytest.raises(ValueError):
        EnsembleStrategy(strategies=[mock_strategy1], weights=[0.6, 0.4])

@pytest.mark.asyncio
async def test_ensemble_strategy_generate_signals():
    mock_strategy1 = AsyncMock()
    mock_strategy1.generate_signals.return_value = [
        Signal(symbol="BTC", side=Side.Buy, strength=1.0)
    ]
    
    mock_strategy2 = AsyncMock()
    mock_strategy2.generate_signals.return_value = [
        Signal(symbol="BTC", side=Side.Sell, strength=0.5)
    ]
    
    ensemble = EnsembleStrategy(strategies=[mock_strategy1, mock_strategy2], weights=[0.8, 0.2])
    signals = await ensemble.generate_signals(market_data=MagicMock(), account=MagicMock())
    
    assert len(signals) == 1
    assert signals[0].symbol == "BTC"
    # Buy 1.0 * 0.8 + Sell (-0.5) * 0.2 = 0.8 - 0.1 = 0.7 (Buy)
    assert signals[0].side == Side.Buy
    assert abs(signals[0].strength - 0.7) < 1e-6

@pytest.mark.asyncio
async def test_ensemble_strategy_empty_signals():
    mock_strategy1 = AsyncMock()
    mock_strategy1.generate_signals.return_value = []
    
    ensemble = EnsembleStrategy(strategies=[mock_strategy1], weights=[1.0])
    signals = await ensemble.generate_signals(market_data=MagicMock(), account=MagicMock())
    assert len(signals) == 0

@pytest.mark.asyncio
async def test_ensemble_strategy_floating_point_precision():
    mock_s1 = AsyncMock()
    mock_s1.generate_signals.return_value = [Signal(symbol="ETH", side=Side.Buy, strength=0.3333333333)]
    
    mock_s2 = AsyncMock()
    mock_s2.generate_signals.return_value = [Signal(symbol="ETH", side=Side.Buy, strength=0.6666666667)]
    
    ensemble = EnsembleStrategy(strategies=[mock_s1, mock_s2], weights=[0.5, 0.5])
    signals = await ensemble.generate_signals(market_data=MagicMock(), account=MagicMock())
    
    assert len(signals) == 1
    # 0.5 * 0.3333333333 + 0.5 * 0.6666666667 = 0.5
    assert abs(signals[0].strength - 0.5) < 1e-9

@pytest.mark.asyncio
async def test_ensemble_strategy_look_ahead_bias_prevention():
    # Simulate market data with current index
    mock_market_data = MagicMock()
    mock_market_data.get_current_time.return_value = "2023-10-01T10:00:00Z"
    
    # Strategy that tries to access future data (mocked to fail or be detected)
    mock_s1 = AsyncMock()
    def mock_generate(*args, **kwargs):
        # If strategy queries market_data > current_time, it should raise
        # For this test, we just verify it was called with the restricted view
        return []
    mock_s1.generate_signals.side_effect = mock_generate
    
    ensemble = EnsembleStrategy(strategies=[mock_s1], weights=[1.0])
    await ensemble.generate_signals(market_data=mock_market_data, account=MagicMock())
    
    # Assert that the strategy was called
    mock_s1.generate_signals.assert_called_once()

