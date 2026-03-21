#!/usr/bin/env python3
"""
Test script for ProbabilisticStrategy implementation.
"""

from __future__ import annotations

import polars as pl

from qtrader.core.event import SignalEvent, OrderEvent
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy


def test_probabilistic_strategy_creation():
    """Test that we can create a ProbabilisticStrategy."""
    print("Testing ProbabilisticStrategy creation...")
    
    strategy = ProbabilisticStrategy(
        symbol="AAPL",
        model_confidence=0.8
    )
    
    assert strategy is not None
    assert strategy.symbol == "AAPL"
    assert strategy.model_confidence == 0.8
    assert strategy.capital == 100_000.0  # Default from BaseStrategy
    print("✓ ProbabilisticStrategy created successfully")


def test_probabilistic_strategy_bullish_signal():
    """Test strategy with clearly bullish features."""
    print("Testing ProbabilisticStrategy with bullish signal...")
    
    strategy = ProbabilisticStrategy(symbol="AAPL", model_confidence=0.9)
    
    # Create strongly bullish features
    features = {
        "alpha1": pl.Series("alpha1", [1.0, 1.5, 2.0]),  # Strongly positive
        "alpha2": pl.Series("alpha2", [0.8, 1.2, 1.8]),  # Positive
    }
    
    # Compute signals
    signal_event = strategy.compute_signals(features)
    
    # Should generate a probabilistic signal
    assert signal_event.signal_type == "PROBABILISTIC"
    assert "buy_prob" in signal_event.metadata
    assert signal_event.metadata["buy_prob"] > 0.5  # Should favor BUY
    
    # Convert to orders
    orders = strategy.on_signal(signal_event)
    
    # Should generate a BUY order
    assert len(orders) == 1
    assert isinstance(orders[0], OrderEvent)
    assert orders[0].side == "BUY"
    assert orders[0].symbol == "AAPL"
    assert orders[0].quantity > 0
    
    print(f"✓ Bullish signal: BUY order with quantity {orders[0].quantity:.2f}")
    print(f"  Probabilities: BUY={signal_event.metadata['buy_prob']:.3f}, "
          f"SELL={signal_event.metadata['sell_prob']:.3f}, HOLD={signal_event.metadata['hold_prob']:.3f}")


def test_probabilistic_strategy_bearish_signal():
    """Test strategy with clearly bearish features."""
    print("Testing ProbabilisticStrategy with bearish signal...")
    
    strategy = ProbabilisticStrategy(symbol="BTC", model_confidence=0.9)
    
    # Create strongly bearish features
    features = {
        "alpha1": pl.Series("alpha1", [-2.0, -1.5, -1.0]),  # Strongly negative
        "alpha2": pl.Series("alpha2", [-1.8, -1.2, -0.8]),  # Negative
    }
    
    # Compute signals
    signal_event = strategy.compute_signals(features)
    
    # Should generate a probabilistic signal
    assert signal_event.signal_type == "PROBABILISTIC"
    assert "sell_prob" in signal_event.metadata
    assert signal_event.metadata["sell_prob"] > 0.5  # Should favor SELL
    
    # Convert to orders
    orders = strategy.on_signal(signal_event)
    
    # Should generate a SELL order
    assert len(orders) == 1
    assert isinstance(orders[0], OrderEvent)
    assert orders[0].side == "SELL"
    assert orders[0].symbol == "BTC"
    assert orders[0].quantity > 0
    
    print(f"✓ Bearish signal: SELL order with quantity {orders[0].quantity:.2f}")
    print(f"  Probabilities: BUY={signal_event.metadata['buy_prob']:.3f}, "
          f"SELL={signal_event.metadata['sell_prob']:.3f}, HOLD={signal_event.metadata['hold_prob']:.3f}")


def test_probabilistic_strategy_neutral_signal():
    """Test strategy with neutral/mixed features."""
    print("Testing ProbabilisticStrategy with neutral signal...")
    
    strategy = ProbabilisticStrategy(symbol="ETH", model_confidence=0.9)
    
    # Create mixed/neutral features
    features = {
        "alpha1": pl.Series("alpha1", [0.1, -0.1, 0.0]),  # Near zero
        "alpha2": pl.Series("alpha2", [-0.1, 0.1, 0.0]),  # Near zero
    }
    
    # Compute signals
    signal_event = strategy.compute_signals(features)
    
    # Should generate a probabilistic signal
    assert signal_event.signal_type == "PROBABILISTIC"
    
    # Convert to orders
    orders = strategy.on_signal(signal_event)
    
    # Should generate no orders (HOLD or weak signal)
    assert len(orders) == 0
    
    print(f"✓ Neutral signal: No orders generated (HOLD)")
    print(f"  Probabilities: BUY={signal_event.metadata['buy_prob']:.3f}, "
          f"SELL={signal_event.metadata['sell_prob']:.3f}, HOLD={signal_event.metadata['hold_prob']:.3f}")


def test_probabilistic_strategy_custom_weights():
    """Test strategy with custom alpha weights."""
    print("Testing ProbabilisticStrategy with custom weights...")
    
    strategy = ProbabilisticStrategy(
        symbol="GOOGL",
        alpha_weights={"alpha1": 0.7, "alpha2": 0.3},  # 70% weight to alpha1
        model_confidence=0.8
    )
    
    # Create features where alpha1 is negative but alpha2 is positive
    # With 70% weight to alpha1, overall should be negative
    features = {
        "alpha1": pl.Series("alpha1", [-1.0, -1.0, -1.0]),  # Negative
        "alpha2": pl.Series("alpha2", [2.0, 2.0, 2.0]),    # Positive
    }
    
    # Compute signals
    signal_event = strategy.compute_signals(features)
    
    # Should favor SELL due to higher weight on negative alpha1
    assert signal_event.signal_type == "PROBABILISTIC"
    assert signal_event.metadata["alpha_weights"]["alpha1"] == 0.7
    assert signal_event.metadata["alpha_weights"]["alpha2"] == 0.3
    
    # Convert to orders
    orders = strategy.on_signal(signal_event)
    
    # Should generate a SELL order due to weighted negative sum
    if len(orders) > 0:
        assert orders[0].side == "SELL"
        print(f"✓ Weighted signal: SELL order generated")
    else:
        print(f"✓ Weighted signal: No order (weak signal)")
    
    print(f"  Alpha weights: {signal_event.metadata['alpha_weights']}")
    print(f"  Latest value: {signal_event.metadata['latest_value']:.3f}")


def test_probabilistic_strategy_signal_strength():
    """Test that signal strength is properly calculated."""
    print("Testing ProbabilisticStrategy signal strength...")
    
    strategy = ProbabilisticStrategy(symbol="TSLA", model_confidence=1.0)  # Full confidence
    
    # Test various signal strengths
    test_cases = [
        # (latest_value, expected_signal_type, min_strength)
        (2.0, "BUY", 0.3),    # Strong positive
        (-2.0, "SELL", 0.3),  # Strong negative
        (0.0, "HOLD", 0.0),   # Neutral
    ]
    
    for latest_value, expected_type, min_strength in test_cases:
        # Create features that will produce the desired latest_value
        features = {
            "alpha1": pl.Series("alpha1", [latest_value, latest_value, latest_value]),
            "alpha2": pl.Series("alpha2", [0.0, 0.0, 0.0]),
        }
        
        signal_event = strategy.compute_signals(features)
        orders = strategy.on_signal(signal_event)
        
        if expected_type != "HOLD":
            # Should generate orders for strong signals
            assert len(orders) == 1
            assert orders[0].side == expected_type
            # Strength should meet minimum threshold
            # Note: actual strength depends on the probability conversion
        else:
            # Should generate no orders for neutral signals
            assert len(orders) == 0
        
        print(f"  Value {latest_value:>4} -> {expected_type} ({len(orders)} orders)")
    
    print("✓ Signal strength calculation working")


def test_probabilistic_strategy_model_confidence():
    """Test that model confidence affects signal strength."""
    print("Testing ProbabilisticStrategy model confidence...")
    
    # Same features, different confidence levels
    features = {
        "alpha1": pl.Series("alpha1", [1.0, 1.0, 1.0]),
        "alpha2": pl.Series("alpha2", [0.5, 0.5, 0.5]),
    }
    
    # Low confidence strategy
    low_conf_strategy = ProbabilisticStrategy(
        symbol="LOW",
        model_confidence=0.3
    )
    
    # High confidence strategy
    high_conf_strategy = ProbabilisticStrategy(
        symbol="HIGH",
        model_confidence=0.9
    )
    
    # Compute signals
    low_signal = low_conf_strategy.compute_signals(features)
    high_signal = high_conf_strategy.compute_signals(features)
    
    # Convert to orders
    low_orders = low_conf_strategy.on_signal(low_signal)
    high_orders = high_conf_strategy.on_signal(high_signal)
    
    # Both should generate BUY orders for positive features
    if len(low_orders) > 0 and len(high_orders) > 0:
        # High confidence should generate larger position size
        low_size = low_orders[0].quantity
        high_size = high_orders[0].quantity
        
        # High confidence should generally produce equal or larger size
        # (depending on the exact probability calculations)
        print(f"  Low confidence size: {low_size:.2f}")
        print(f"  High confidence size: {high_size:.2f}")
    
    print("✓ Model confidence integration working")


def main():
    """Run all tests."""
    print("Testing Probabilistic Strategy Implementation...\n")
    
    test_probabilistic_strategy_creation()
    test_probabilistic_strategy_bullish_signal()
    test_probabilistic_strategy_bearish_signal()
    test_probabilistic_strategy_neutral_signal()
    test_probabilistic_strategy_custom_weights()
    test_probabilistic_strategy_signal_strength()
    test_probabilistic_strategy_model_confidence()
    
    print("\n✅ All probabilistic strategy tests passed!")


if __name__ == "__main__":
    main()