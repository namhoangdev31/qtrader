"""Unit tests for the meta-learning engine."""
import tempfile
from collections import deque
from unittest.mock import MagicMock

import numpy as np
import polars as pl

from qtrader.ml.meta_learning_engine import MetaLearningEngine


def test_meta_learning_engine_initialization():
    """Test meta-learning engine initialization."""
    engine = MetaLearningEngine(
        window_size=50,
        min_trades=10,
        temperature=1.0,
        strategy_weights=(0.4, 0.3, 0.2, 0.1),
        decay_penalty=0.5,
        min_weight=0.01,
        max_weight=0.50,
    )
    
    assert engine.window_size == 50
    assert engine.min_trades == 10
    assert engine.temperature == 1.0
    assert engine.w_sharpe == 0.4
    assert engine.w_pnl == 0.3
    assert engine.w_dd == 0.2
    assert engine.w_hit == 0.1
    assert engine.decay_penalty == 0.5
    assert engine.min_weight == 0.01
    assert engine.max_weight == 0.50
    assert engine.current_regime is None
    assert engine.regime_probability == 0.0


def test_update_performance():
    """Test updating performance metrics."""
    engine = MetaLearningEngine(window_size=5, min_trades=2)
    
    strategy_perf = {
        'strategy_a': {'sharpe': 1.2, 'pnl_mean': 0.05, 'drawdown': 0.1, 'hit_ratio': 0.6},
        'strategy_b': {'sharpe': 0.8, 'pnl_mean': 0.03, 'drawdown': 0.08, 'hit_ratio': 0.5}
    }
    
    feature_perf = {
        'feature_1': (0.3, 0.1),
        'feature_2': (0.2, 0.05)
    }
    
    engine.update(strategy_perf, feature_perf, 'regime_1', 0.8)
    
    # Check that history was updated
    assert 'strategy_a' in engine.global_strategy_history
    assert len(engine.global_strategy_history['strategy_a']) == 1
    assert engine.global_strategy_history['strategy_a'][0] == (1.2, 0.05, 0.1, 0.6)
    
    assert 'feature_1' in engine.global_feature_history
    assert len(engine.global_feature_history['feature_1']) == 1
    assert engine.global_feature_history['feature_1'][0] == (0.3, 0.1)
    
    # Check regime-specific history
    assert 'regime_1' in engine.regime_strategy_history
    assert 'strategy_a' in engine.regime_strategy_history['regime_1']
    assert len(engine.regime_strategy_history['regime_1']['strategy_a']) == 1
    assert engine.regime_strategy_history['regime_1']['strategy_a'][0] == (1.2, 0.05, 0.1, 0.6)
    
    assert 'regime_1' in engine.regime_feature_history
    assert 'feature_1' in engine.regime_feature_history['regime_1']
    assert len(engine.regime_feature_history['regime_1']['feature_1']) == 1
    assert engine.regime_feature_history['regime_1']['feature_1'][0] == (0.3, 0.1)
    
    assert engine.current_regime == 'regime_1'
    assert engine.regime_probability == 0.8


def test_compute_strategy_scores():
    """Test computing strategy scores from history."""
    engine = MetaLearningEngine(window_size=5, min_trades=2)
    
    # Add some history
    history = {
        'strategy_a': deque([(1.0, 0.05, 0.1, 0.6), (1.2, 0.06, 0.08, 0.7)], maxlen=5),
        'strategy_b': deque([(0.5, 0.02, 0.15, 0.4), (0.6, 0.03, 0.12, 0.5)], maxlen=5)
    }
    
    scores = engine._compute_strategy_scores(history)
    
    # Strategy A: 0.4*1.1 + 0.3*0.055 - 0.2*0.09 + 0.1*0.65 = 0.44 + 0.0165 - 0.018 + 0.065 = 0.5035
    # Strategy B: 0.4*0.55 + 0.3*0.025 - 0.2*0.135 + 0.1*0.45 = 0.22 + 0.0075 - 0.027 + 0.045 = 0.2455
    assert abs(scores['strategy_a'] - 0.5035) < 0.001
    assert abs(scores['strategy_b'] - 0.2455) < 0.001


def test_compute_feature_scores():
    """Test computing feature scores from history."""
    engine = MetaLearningEngine(window_size=5, min_trades=2, decay_penalty=0.5)
    
    # Add some history
    history = {
        'feature_1': deque([(0.3, 0.1), (0.4, 0.05)], maxlen=5),
        'feature_2': deque([(0.1, 0.2), (0.2, 0.15)], maxlen=5)
    }
    
    scores = engine._compute_feature_scores(history)
    
    # Feature 1: 0.35 - 0.5*0.075 = 0.35 - 0.0375 = 0.3125
    # Feature 2: 0.15 - 0.5*0.175 = 0.15 - 0.0875 = 0.0625
    assert abs(scores['feature_1'] - 0.3125) < 0.001
    assert abs(scores['feature_2'] - 0.0625) < 0.001


def test_softmax():
    """Test softmax computation."""
    engine = MetaLearningEngine()
    
    # Test with normal scores
    scores = {'a': 1.0, 'b': 2.0, 'c': 3.0}
    result = engine._softmax(scores)
    
    # Should sum to 1.0
    assert abs(sum(result.values()) - 1.0) < 0.0001
    
    # c should have highest weight
    assert result['c'] > result['b'] > result['a']
    
    # Test with all zeros
    scores_zero = {'a': 0.0, 'b': 0.0, 'c': 0.0}
    result_zero = engine._softmax(scores_zero)
    
    # Should be uniform distribution
    assert abs(result_zero['a'] - 1.0/3.0) < 0.0001
    assert abs(result_zero['b'] - 1.0/3.0) < 0.0001
    assert abs(result_zero['c'] - 1.0/3.0) < 0.0001
    
    # Test with empty scores
    result_empty = engine._softmax({})
    assert result_empty == {}


def test_clip_and_normalize():
    """Test weight clipping and normalization."""
    engine = MetaLearningEngine(min_weight=0.1, max_weight=0.5)
    
    # Test normal case
    weights = {'a': 0.2, 'b': 0.3, 'c': 0.5}
    result = engine._clip_and_normalize(weights)
    
    # Should sum to 1.0
    assert abs(sum(result.values()) - 1.0) < 0.0001
    
    # Test clipping
    weights_clip = {'a': 0.05, 'b': 0.6, 'c': 0.3}  # a too low, b too high
    result_clip = engine._clip_and_normalize(weights_clip)
    
    # a should be clipped to 0.1, b to 0.5
    assert result_clip['a'] >= 0.099  # Allow small floating point difference
    assert result_clip['b'] <= 0.501  # Allow small floating point difference
    assert abs(sum(result_clip.values()) - 1.0) < 0.0001
    
    # Test zero sum case
    weights_zero = {'a': 0.0, 'b': 0.0}
    result_zero = engine._clip_and_normalize(weights_zero)
    
    # Should be uniform
    assert abs(result_zero['a'] - 0.5) < 0.0001
    assert abs(result_zero['b'] - 0.5) < 0.0001


def test_average_sharpe():
    """Test average Sharpe calculation."""
    engine = MetaLearningEngine()
    
    # Test with data
    history = {
        'strategy_a': deque([(1.0, 0.05, 0.1, 0.6), (2.0, 0.06, 0.08, 0.7)], maxlen=5),
        'strategy_b': deque([(0.5, 0.02, 0.15, 0.4), (1.5, 0.03, 0.12, 0.5)], maxlen=5)
    }
    
    avg_sharpe = engine._average_sharpe(history)
    # (1.0 + 2.0 + 0.5 + 1.5) / 4 = 5.0 / 4 = 1.25
    assert abs(avg_sharpe - 1.25) < 0.0001
    
    # Test with empty history
    empty_history = {}
    assert engine._average_sharpe(empty_history) == 0.0
    
    # Test with empty deques
    empty_deque_history = {'strategy_a': deque(maxlen=5)}
    assert engine._average_sharpe(empty_deque_history) == 0.0


def test_sigmoid():
    """Test sigmoid function."""
    engine = MetaLearningEngine()
    
    # Test known values
    assert abs(engine._sigmoid(0) - 0.5) < 0.0001
    assert abs(engine._sigmoid(1) - 0.731) < 0.001
    assert abs(engine._sigmoid(-1) - 0.269) < 0.001
    
    # Test large values
    assert abs(engine._sigmoid(10) - 1.0) < 0.0001
    assert abs(engine._sigmoid(-10) - 0.0) < 0.0001


def test_get_weights_insufficient_data():
    """Test get_weights with insufficient data."""
    engine = MetaLearningEngine(window_size=5, min_trades=10)  # Need 10 trades
    
    # Add less than min_trades
    strategy_perf = {
        'strategy_a': {'sharpe': 1.2, 'pnl_mean': 0.05, 'drawdown': 0.1, 'hit_ratio': 0.6}
    }
    feature_perf = {
        'feature_1': (0.3, 0.1)
    }
    
    engine.update(strategy_perf, feature_perf, 'regime_1', 0.8)
    
    weights = engine.get_weights()
    
    # Should fall back to equal weights
    assert 'strategy_weights' in weights
    assert 'feature_weights' in weights
    assert 'confidence_multiplier' in weights
    
    # With only one strategy, should get weight 1.0
    assert abs(weights['strategy_weights']['strategy_a'] - 1.0) < 0.0001
    
    # With only one feature, should get weight 1.0
    assert abs(weights['feature_weights']['feature_1'] - 1.0) < 0.0001
    
    # Confidence should be sigmoid(1.2) * 0.8
    expected_confidence = engine._sigmoid(1.2) * 0.8
    assert abs(weights['confidence_multiplier'] - expected_confidence) < 0.0001


def test_get_weights_sufficient_data():
    """Test get_weights with sufficient data."""
    engine = MetaLearningEngine(window_size=5, min_trades=2)
    
    # Add sufficient data
    strategy_perf = {
        'strategy_a': {'sharpe': 1.2, 'pnl_mean': 0.05, 'drawdown': 0.1, 'hit_ratio': 0.6},
        'strategy_b': {'sharpe': 0.8, 'pnl_mean': 0.03, 'drawdown': 0.08, 'hit_ratio': 0.5}
    }
    
    # Add multiple times to reach min_trades
    for _ in range(3):
        engine.update(strategy_perf, {}, 'regime_1', 0.8)
    
    weights = engine.get_weights()
    
    # Should have computed weights
    assert 'strategy_weights' in weights
    assert len(weights['strategy_weights']) == 2
    assert abs(sum(weights['strategy_weights'].values()) - 1.0) < 0.0001
    
    # Strategy A should have higher weight due to better Sharpe
    assert weights['strategy_weights']['strategy_a'] > weights['strategy_weights']['strategy_b']
    
    # Confidence should be reasonable
    assert 0.0 <= weights['confidence_multiplier'] <= 1.0


def test_regime_blending():
    """Test regime-specific weight blending."""
    engine = MetaLearningEngine(window_size=5, min_trades=2)
    
    # Add global data
    strategy_perf_global = {
        'strategy_a': {'sharpe': 1.0, 'pnl_mean': 0.04, 'drawdown': 0.1, 'hit_ratio': 0.5},
        'strategy_b': {'sharpe': 1.0, 'pnl_mean': 0.04, 'drawdown': 0.1, 'hit_ratio': 0.5}
    }
    
    # Add regime-specific data that favors strategy_a
    strategy_perf_regime = {
        'strategy_a': {'sharpe': 2.0, 'pnl_mean': 0.08, 'drawdown': 0.05, 'hit_ratio': 0.7},
        'strategy_b': {'sharpe': 0.5, 'pnl_mean': 0.02, 'drawdown': 0.15, 'hit_ratio': 0.4}
    }
    
    # Build up global history
    for _ in range(3):
        engine.update(strategy_perf_global, {}, 'regime_1', 0.5)  # 50% regime probability
    
    # Build up regime-specific history
    for _ in range(3):
        engine.update(strategy_perf_regime, {}, 'regime_1', 0.5)
    
    weights = engine.get_weights()
    
    # With regime blending, strategy_a should be favored due to better regime performance
    # but not as much as if we were 100% in that regime
    assert weights['strategy_weights']['strategy_a'] > weights['strategy_weights']['strategy_b']


def test_update_regime_info():
    """Test updating regime info without affecting performance history."""
    engine = MetaLearningEngine(window_size=5, min_trades=2)
    
    # Add some performance data
    strategy_perf = {
        'strategy_a': {'sharpe': 1.2, 'pnl_mean': 0.05, 'drawdown': 0.1, 'hit_ratio': 0.6}
    }
    feature_perf = {
        'feature_1': (0.3, 0.1)
    }
    
    engine.update(strategy_perf, feature_perf, 'regime_1', 0.8)
    
    # Store original regime
    original_regime = engine.current_regime
    original_prob = engine.regime_probability
    
    # Update regime info only
    engine.update_regime_info('regime_2', 0.9)
    
    # Regime should be updated
    assert engine.current_regime == 'regime_2'
    assert engine.regime_probability == 0.9
    
    # Performance history should be unchanged
    assert len(engine.global_strategy_history['strategy_a']) == 1
    assert len(engine.global_feature_history['feature_1']) == 1
    assert len(engine.regime_strategy_history['regime_1']['strategy_a']) == 1
    assert len(engine.regime_feature_history['regime_1']['feature_1']) == 1
    # No history for regime_2 yet
    assert 'regime_2' not in engine.regime_strategy_history or \
           len(engine.regime_strategy_history.get('regime_2', {}).get('strategy_a', [])) == 0


if __name__ == '__main__':
    test_meta_learning_engine_initialization()
    test_update_performance()
    test_compute_strategy_scores()
    test_compute_feature_scores()
    test_softmax()
    test_clip_and_normalize()
    test_average_sharpe()
    test_sigmoid()
    test_get_weights_insufficient_data()
    test_get_weights_sufficient_data()
    test_regime_blending()
    test_update_regime_info()
    print('All tests passed!')