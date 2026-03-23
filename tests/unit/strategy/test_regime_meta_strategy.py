import pytest
from unittest.mock import MagicMock
from qtrader.strategy.regime_meta_strategy import RegimeMetaStrategy
from qtrader.core.types import Signal, Side

def test_regime_meta_strategy_init():
    mock_detector = MagicMock()
    mock_strategies = {"bull": MagicMock(), "bear": MagicMock()}
    meta = RegimeMetaStrategy(regime_detector=mock_detector, strategies=mock_strategies)
    assert meta.regime_detector == mock_detector
    assert "bull" in meta.strategies

@pytest.mark.asyncio
async def test_regime_meta_strategy_generate_signals():
    mock_detector = MagicMock()
    mock_detector.detect.return_value = "bull"
    
    mock_bull_strategy = AsyncMock()
    mock_bull_strategy.generate_signals.return_value = [Signal(symbol="BTC", side=Side.Buy, strength=1.0)]
    
    mock_bear_strategy = AsyncMock()
    
    meta = RegimeMetaStrategy(
        regime_detector=mock_detector, 
        strategies={"bull": mock_bull_strategy, "bear": mock_bear_strategy}
    )
    
    signals = await meta.generate_signals(market_data=MagicMock(), account=MagicMock())
    assert len(signals) == 1
    assert signals[0].side == Side.Buy
    mock_bull_strategy.generate_signals.assert_called_once()
    mock_bear_strategy.generate_signals.assert_not_called()

def test_regime_meta_strategy_unknown_regime():
    mock_detector = MagicMock()
    mock_detector.detect.return_value = "unknown"
    mock_strategies = {"bull": MagicMock()}
    
    meta = RegimeMetaStrategy(regime_detector=mock_detector, strategies=mock_strategies)
    # Should probably raise or return empty
    pass
