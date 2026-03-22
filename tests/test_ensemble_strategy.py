"""Unit tests for the ensemble strategy."""
from unittest.mock import MagicMock

import polars as pl

from qtrader.strategy.ensemble_strategy import EnsembleStrategy


def test_ensemble_strategy_initialization():
    """Test ensemble strategy initialization."""
    # Create mock strategies
    strategy1 = MagicMock()
    strategy1.compute_signals.return_value = MagicMock(
        symbol="TEST",
        signal_type="BUY",
        strength=0.8,
        metadata={'buy_prob': 0.8, 'sell_prob': 0.1, 'hold_prob': 0.1}
    )
    
    strategy2 = MagicMock()
    strategy2.compute_signals.return_value = MagicMock(
        symbol="TEST",
        signal_type="SELL",
        strength=0.6,
        metadata={'buy_prob': 0.1, 'sell_prob': 0.6, 'hold_prob': 0.3}
    )
    
    strategies = [strategy1, strategy2]
    
    ensemble = EnsembleStrategy(
        strategies=strategies,
        performance_window=20,
        min_weight=0.05,
        max_weight=0.5,
        rebalance_frequency=5,
        enable_meta_learning=True,
        meta_learning_window=50,
        meta_learning_min_trades=10
    )
    
    assert len(ensemble.strategies) == 2
    assert ensemble.performance_window == 20
    assert ensemble.min_weight == 0.05
    assert ensemble.max_weight == 0.5
    assert ensemble.rebalance_frequency == 5
    assert ensemble.enable_meta_learning is True
    # Meta-learning engine may be None if dependencies are not available
    # In that case, it should fall back to legacy weighting
    if ensemble.meta_learning_engine is None:
        # Should still have legacy weights initialized
        assert ensemble._strategy_weights == {0: 0.5, 1: 0.5}
    else:
        # If available, should be properly initialized
        assert ensemble.meta_learning_engine is not None
    assert ensemble._signal_count == 0


def test_ensemble_strategy_compute_signals():
    """Test ensemble strategy signal computation."""
    # Create mock strategies
    strategy1 = MagicMock()
    strategy1.compute_signals.return_value = MagicMock(
        symbol="TEST",
        signal_type="BUY",
        strength=0.8,
        metadata={'buy_prob': 0.8, 'sell_prob': 0.1, 'hold_prob': 0.1}
    )
    
    strategy2 = MagicMock()
    strategy2.compute_signals.return_value = MagicMock(
        symbol="TEST",
        signal_type="SELL",
        strength=0.6,
        metadata={'buy_prob': 0.1, 'sell_prob': 0.6, 'hold_prob': 0.3}
    )
    
    strategies = [strategy1, strategy2]
    
    ensemble = EnsembleStrategy(
        strategies=strategies,
        enable_meta_learning=False  # Disable meta-learning for simpler test
    )
    
    # Create dummy features
    features = {
        'feature1': pl.Series([1.0, 2.0, 3.0]),
        'feature2': pl.Series([0.5, 1.0, 1.5])
    }
    
    # Compute signals
    signal = ensemble.compute_signals(features)
    
    # Check that we got a signal
    assert signal is not None
    assert hasattr(signal, 'symbol')
    assert hasattr(signal, 'signal_type')
    assert hasattr(signal, 'strength')
    assert hasattr(signal, 'metadata')
    assert signal.metadata is not None
    
    # Check that strategies were called
    strategy1.compute_signals.assert_called_once()
    strategy2.compute_signals.assert_called_once()
    
    # Check that weights are present in metadata
    assert 'strategy_weights' in signal.metadata
    assert len(signal.metadata['strategy_weights']) == 2
    
    # Check that signal components are present
    assert 'signal_components' in signal.metadata
    assert len(signal.metadata['signal_components']) == 2


def test_ensemble_strategy_with_meta_learning():
    """Test ensemble strategy with meta-learning enabled."""
    # Create mock strategies
    strategy1 = MagicMock()
    strategy1.__class__.__name__ = "StrategyA"
    strategy1.compute_signals.return_value = MagicMock(
        symbol="TEST",
        signal_type="BUY",
        strength=0.8,
        metadata={'buy_prob': 0.8, 'sell_prob': 0.1, 'hold_prob': 0.1}
    )
    
    strategy2 = MagicMock()
    strategy2.__class__.__name__ = "StrategyB"
    strategy2.compute_signals.return_value = MagicMock(
        symbol="TEST",
        signal_type="SELL",
        strength=0.6,
        metadata={'buy_prob': 0.1, 'sell_prob': 0.6, 'hold_prob': 0.3}
    )
    
    strategies = [strategy1, strategy2]
    
    ensemble = EnsembleStrategy(
        strategies=strategies,
        enable_meta_learning=True,
        meta_learning_window=5,
        meta_learning_min_trades=2
    )
    
    # Create dummy features
    features = {
        'feature1': pl.Series([1.0, 2.0, 3.0]),
        'feature2': pl.Series([0.5, 1.0, 1.5])
    }
    
    # Compute signals multiple times to build up history
    for i in range(5):
        signal = ensemble.compute_signals(features)
        
        # Update regime info periodically
        if i % 2 == 0:
            ensemble.update_regime_info("bull", 0.8)
        else:
            ensemble.update_regime_info("bear", 0.3)
    
    # Check that we got a signal
    assert signal is not None
    assert hasattr(signal, 'symbol')
    assert hasattr(signal, 'signal_type')
    assert hasattr(signal, 'strength')
    assert hasattr(signal, 'metadata')
    
    # Check that strategies were called
    assert strategy1.compute_signals.call_count == 5
    assert strategy2.compute_signals.call_count == 5
    
    # Check that weights are present in metadata
    assert 'strategy_weights' in signal.metadata
    assert len(signal.metadata['strategy_weights']) == 2


def test_update_regime_info():
    """Test updating regime information."""
    # Create mock strategies
    strategy1 = MagicMock()
    strategy2 = MagicMock()
    
    strategies = [strategy1, strategy2]
    
    ensemble = EnsembleStrategy(
        strategies=strategies,
        enable_meta_learning=True
    )
    
    # Update regime info
    ensemble.update_regime_info("bull", 0.8)
    
    # Check that regime info was stored
    assert ensemble._current_regime == "bull"
    assert ensemble._regime_probability == 0.8


if __name__ == '__main__':
    test_ensemble_strategy_initialization()
    test_ensemble_strategy_compute_signals()
    test_ensemble_strategy_with_meta_learning()
    test_update_regime_info()
    print('All tests passed!')