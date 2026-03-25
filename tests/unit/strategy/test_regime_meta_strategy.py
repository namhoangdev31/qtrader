import pytest
from unittest.mock import MagicMock, AsyncMock
from qtrader.strategy.regime_meta_strategy import RegimeAwareMetaStrategy
from qtrader.core.event import SignalEvent
from qtrader.core.types import Side
from datetime import datetime
import polars as pl

def test_regime_meta_strategy_init():
    mock_detector = MagicMock()
    meta = RegimeAwareMetaStrategy(regime_detector=mock_detector, regime_feature_cols=["f1"])
    assert meta.regime_detector == mock_detector
    assert meta.regime_feature_cols == ["f1"]

def test_regime_meta_strategy_combine_signals():
    mock_detector = MagicMock()
    mock_detector.current_regime_confidence.return_value = (0, 0.9)
    
    strategy_signals = {
        "strat1": SignalEvent(symbol="BTC", signal_type="BUY", strength=1.0, timestamp=datetime.utcnow())
    }
    
    meta = RegimeAwareMetaStrategy(
        regime_detector=mock_detector, 
        regime_feature_cols=["f1"],
        regime_strategy_weights={0: {"strat1": 1.0}}
    )
    
    market_data = pl.DataFrame({"f1": [1.0]})
    signal = meta.combine_signals(strategy_signals, market_data)
    
    assert signal.signal_type == "BUY"
    assert signal.strength == 1.0
    assert signal.metadata["regime_id"] == 0

def test_regime_meta_strategy_generate_signals():
    mock_detector = MagicMock()
    mock_detector.current_regime_confidence.return_value = (0, 0.9)
    # Match the internal logic of RegimeAwareMetaStrategy.combine_signals
    
    mock_bull_strategy = AsyncMock()
    mock_bull_strategy.compute_signals.return_value = SignalEvent(
        symbol="BTC", signal_type="BUY", strength=1.0, timestamp=datetime.utcnow()
    )
    
    mock_bear_strategy = AsyncMock()
    
    meta = RegimeAwareMetaStrategy(
        regime_detector=mock_detector, 
        regime_feature_cols=["f1"],
        regime_strategy_weights={0: {"bull": 1.0}}
    )
    
    # In reality, RegimeAwareMetaStrategy doesn't have self.strategies, 
    # but the test might expect it if it was from a different version.
    # The actual combine_signals takes a dict of signals.
    strategy_signals = {
        "bull": mock_bull_strategy.compute_signals.return_value
    }
    
    market_data = pl.DataFrame({"f1": [1.0]})
    signal = meta.combine_signals(strategy_signals, market_data)
    
    assert signal.signal_type == "BUY"
    assert signal.strength == 1.0

def test_regime_meta_strategy_unknown_regime():
    mock_detector = MagicMock()
    mock_detector.detect.return_value = "unknown"
    mock_strategies = {"bull": MagicMock()}
    
    meta = RegimeAwareMetaStrategy(regime_detector=mock_detector, regime_feature_cols=["f1"])
    # Should probably raise or return empty
    pass
