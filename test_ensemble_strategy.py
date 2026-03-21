#!/usr/bin/env python3
"""
Test script for EnsembleStrategy implementation.
"""

from __future__ import annotations

import polars as pl

from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.core.event import SignalEvent


def test_ensemble_strategy_creation():
    """Test that we can create an EnsembleStrategy."""
    print("Testing EnsembleStrategy creation...")
    
    # Create sub-strategies
    strategy1 = ProbabilisticStrategy(symbol="AAPL", model_confidence=0.7)
    strategy2 = ProbabilisticStrategy(symbol="AAPL", model_confidence=0.8)
    
    # Create ensemble
    ensemble = EnsembleStrategy(
        strategies=[strategy1, strategy2]
    )
    
    assert ensemble is not None
    assert len(ensemble.strategies) == 2
    print("✓ EnsembleStrategy created successfully")


def test_ensemble_strategy_compute_signals():
    """Test that ensemble can compute signals from features."""
    print("Testing EnsembleStrategy compute_signals...")
    
    # Create sub-strategies
    strategy1 = ProbabilisticStrategy(symbol="MSFT", model_confidence=0.9)
    strategy2 = ProbabilisticStrategy(symbol="MSFT", model_confidence=0.9)
    
    # Create ensemble
    ensemble = EnsembleStrategy(strategies=[strategy1, strategy2])
    
    # Create bullish features
    features = {
        "alpha1": pl.Series("alpha1", [1.5, 2.0, 2.5]),  # Strongly positive
        "alpha2": pl.Series("alpha2", [1.0, 1.5, 2.0]),  # Positive
    }
    
    # Compute ensemble signal
    signal_event = ensemble.compute_signals(features)
    
    # Should generate an ensemble signal
    assert signal_event.signal_type == "ENSEMBLE"
    assert 'buy_prob' in signal_event.metadata
    assert 'sell_prob' in signal_event.metadata
    assert 'hold_prob' in signal_event.metadata
    assert 'strategy_weights' in signal_event.metadata
    
    # Probabilities should sum to approximately 1.0
    total_prob = (signal_event.metadata['buy_prob'] + 
                  signal_event.metadata['sell_prob'] + 
                  signal_event.metadata['hold_prob'])
    assert abs(total_prob - 1.0) < 0.01
    
    # Strength should be available as an attribute
    assert hasattr(signal_event, 'strength')
    
    print(f"✓ Ensemble signal: BUY={signal_event.metadata['buy_prob']:.3f}, "
          f"SELL={signal_event.metadata['sell_prob']:.3f}, HOLD={signal_event.metadata['hold_prob']:.3f}")
    print(f"  Strength: {signal_event.strength:.3f}")


def test_ensemble_strategy_mixed_signals():
    """Test ensemble with mixed signals from sub-strategies."""
    print("Testing EnsembleStrategy with mixed signals...")
    
    # Create sub-strategies
    strategy1 = ProbabilisticStrategy(symbol="TSLA", model_confidence=0.9)  # Will be bullish
    strategy2 = ProbabilisticStrategy(symbol="TSLA", model_confidence=0.9)  # Will be bearish
    
    # Create ensemble
    ensemble = EnsembleStrategy(strategies=[strategy1, strategy2])
    
    # Create mixed features: one strategy bullish, one bearish
    features = {
        "alpha1": pl.Series("alpha1", [2.0, 2.0, 2.0]),   # Strongly positive
        "alpha2": pl.Series("alpha2", [-2.0, -2.0, -2.0]), # Strongly negative
    }
    
    # Compute ensemble signal
    signal_event = ensemble.compute_signals(features)
    
    # Should generate an ensemble signal
    assert signal_event.signal_type == "ENSEMBLE"
    
    # Check that we have probabilities
    buy_prob = signal_event.metadata['buy_prob']
    sell_prob = signal_event.metadata['sell_prob']
    hold_prob = signal_event.metadata['hold_prob']
    
    print(f"✓ Mixed ensemble signal: BUY={buy_prob:.3f}, SELL={sell_prob:.3f}, HOLD={hold_prob:.3f}")
    
    # With opposite signals of equal strength, we expect something close to neutral
    # (though exact values depend on the combination method)
    assert 0.2 <= buy_prob <= 0.8
    assert 0.2 <= sell_prob <= 0.8
    assert 0.0 <= hold_prob <= 1.0


def test_ensemble_strategy_weight_adaptation():
    """Test that ensemble weights adapt based on performance."""
    print("Testing EnsembleStrategy weight adaptation...")
    
    # Create sub-strategies with different performance profiles
    strategy1 = ProbabilisticStrategy(symbol="AMZN", model_confidence=0.8)  # Consistent performer
    strategy2 = ProbabilisticStrategy(symbol="AMZN", model_confidence=0.6)  # Inconsistent performer
    
    # Create ensemble
    ensemble = EnsembleStrategy(
        strategies=[strategy1, strategy2],
        performance_window=5,
        rebalance_frequency=3
    )
    
    # Store initial weights
    initial_weights = ensemble._strategy_weights.copy()
    print(f"  Initial weights: {initial_weights}")
    
    # Simulate several signals where strategy1 performs better (higher strength)
    features = {
        "alpha1": pl.Series("alpha1", [1.0, 1.0, 1.0, 1.0, 1.0]),  # Consistently positive
        "alpha2": pl.Series("alpha2", [0.5, 0.5, 0.5, 0.5, 0.5]), # Moderately positive
    }
    
    # Process multiple signals to trigger weight adaptation
    for i in range(10):
        signal_event = ensemble.compute_signals(features)
        
        # Update performance tracking manually (simulating what would happen with actual signals)
        # In a real system, this would be triggered by the signals themselves
        strategy_signals = {
            0: strategy1.compute_signals(features),
            1: strategy2.compute_signals(features)
        }
        ensemble._update_performance(strategy_signals)
        
        # Rebalance if needed
        ensemble._signal_count += 1
        if ensemble._signal_count % ensemble.rebalance_frequency == 0:
            ensemble._rebalance_weights()
    
    # Check final weights
    final_weights = ensemble._strategy_weights.copy()
    print(f"  Final weights: {final_weights}")
    
    # Strategy 1 should have higher weight due to better performance
    # (though exact values depend on the algorithm)
    print(f"  Strategy 1 weight: {final_weights[0]:.3f}")
    print(f"  Strategy 2 weight: {final_weights[1]:.3f}")
    
    # The better performing strategy (strategy 0) should have higher weight
    assert final_weights[0] > final_weights[1], "Better performing strategy should have higher weight"
    
    # Weights should sum to approximately 1.0
    total_weight = sum(final_weights.values())
    assert abs(total_weight - 1.0) < 0.01
    
    print("✓ Ensemble weight adaptation mechanism tested")


def test_ensemble_strategy_empty_strategies():
    """Test ensemble with empty strategies list."""
    print("Testing EnsembleStrategy with empty strategies...")
    
    ensemble = EnsembleStrategy(strategies=[])
    
    # Create dummy features
    features = {
        "alpha1": pl.Series("alpha1", [1.0, 2.0, 3.0]),
        "alpha2": pl.Series("alpha2", [0.1, 0.2, 0.3])
    }
    
    # Compute signals
    signal_event = ensemble.compute_signals(features)
    
    # Should handle gracefully (though behavior may vary)
    # For now, we just check it doesn't crash
    assert signal_event is not None
    assert hasattr(signal_event, 'signal_type')
    
    print("✓ Empty strategies handled gracefully")


def test_ensemble_strategy_single_strategy():
    """Test ensemble with single strategy."""
    print("Testing EnsembleStrategy with single strategy...")
    
    # Create single sub-strategy
    strategy = ProbabilisticStrategy(symbol="SINGLE", model_confidence=0.9)
    
    # Create ensemble
    ensemble = EnsembleStrategy(strategies=[strategy])
    
    # Create features
    features = {
        "alpha1": pl.Series("alpha1", [1.0, 2.0, 3.0]),
        "alpha2": pl.Series("alpha2", [0.5, 0.5, 0.5])
    }
    
    # Compute ensemble signal
    signal_event = ensemble.compute_signals(features)
    
    # Should generate an ensemble signal
    assert signal_event.signal_type == "ENSEMBLE"
    
    # The ensemble should essentially replicate the single strategy
    # (though there may be small differences due to the ensemble framework)
    individual_signal = strategy.compute_signals(features)
    
    print(f"✓ Single strategy ensemble: {len(ensemble.strategies)} strategy")
    print(f"  Individual signal strength: {individual_signal.strength:.3f}")
    print(f"  Ensemble signal strength: {signal_event.strength:.3f}")
    
    # Both should be non-zero for positive features
    assert individual_signal.strength > 0
    assert signal_event.strength > 0


def main():
    """Run all tests."""
    print("Testing Ensemble Strategy Implementation...\n")
    
    test_ensemble_strategy_creation()
    test_ensemble_strategy_compute_signals()
    test_ensemble_strategy_mixed_signals()
    test_ensemble_strategy_weight_adaptation()
    test_ensemble_strategy_empty_strategies()
    test_ensemble_strategy_single_strategy()
    
    print("\n✅ All ensemble strategy tests passed!")


if __name__ == "__main__":
    main()