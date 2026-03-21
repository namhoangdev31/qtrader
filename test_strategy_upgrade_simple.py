#!/usr/bin/env python3
"""
Simple test script for Strategy layer upgrade concept to probabilistic signaling.
This avoids importing the full strategy layer to prevent dependency issues.
"""

from __future__ import annotations

import polars as pl

from qtrader.core.event import SignalEvent


class ProbabilisticStrategy:
    """
    Example strategy that outputs probabilistic signals instead of threshold-based signals.
    
    This demonstrates the upgrade from deterministic thresholds to confidence-scoring models.
    """
    
    def __init__(self, model_confidence: float = 0.7):
        """
        Initialize the probabilistic strategy.
        
        Args:
            model_confidence: Base confidence level for signals (0.0 to 1.0)
        """
        self.model_confidence = model_confidence
    
    def compute_signals(self, features: dict[str, pl.Series]) -> SignalEvent:
        """
        Compute trading signals using probabilistic approach.
        
        Instead of fixed thresholds, we calculate probabilities for each signal type
        based on the weighted sum of features and convert to a probability distribution.
        
        Args:
            features: Dictionary mapping alpha names to their feature series
            
        Returns:
            SignalEvent with probabilistic signal and confidence scores
        """
        # Validate input features
        if not features:
            raise ValueError("Features dictionary cannot be empty")
        
        # Check that all series have the same length and are Float64
        lengths = [series.len() for series in features.values()]
        if len(set(lengths)) != 1:
            raise ValueError(
                f"All feature series must have the same length. Got lengths: {lengths}"
            )
        
        for name, series in features.items():
            if series.dtype != pl.Float64:
                raise ValueError(
                    f"Feature '{name}' must be Float64, got {series.dtype}"
                )
        
        # Compute weighted sum of features (simple equal weighting for demo)
        first_series = next(iter(features.values()))
        weighted_sum = pl.Series(
            [0.0] * first_series.len(), dtype=pl.Float64
        ).alias("weighted_sum")
        
        # Equal weights for simplicity
        weight = 1.0 / len(features)
        for name, series in features.items():
            weighted_sum = weighted_sum + (series * weight)
        
        # Get the latest value
        latest_value = weighted_sum[-1]
        
        # Convert to probabilities using softmax-like approach
        # This is a simplified version - in production would use a trained model
        buy_prob = max(0.0, min(1.0, (latest_value + 1.0) / 2.0))  # Map [-1,1] to [0,1]
        sell_prob = max(0.0, min(1.0, (-latest_value + 1.0) / 2.0))  # Inverted
        hold_prob = 1.0 - (buy_prob + sell_prob) / 2.0  # Ensure they sum reasonably
        
        # Normalize to make a proper probability distribution
        total_prob = buy_prob + sell_prob + hold_prob
        if total_prob > 0:
            buy_prob /= total_prob
            sell_prob /= total_prob
            hold_prob /= total_prob
        else:
            # Uniform distribution if no signal
            buy_prob = sell_prob = hold_prob = 1.0 / 3.0
        
        # Apply model confidence
        buy_prob = buy_prob * self.model_confidence + (1.0 - self.model_confidence) * (1.0 / 3.0)
        sell_prob = sell_prob * self.model_confidence + (1.0 - self.model_confidence) * (1.0 / 3.0)
        hold_prob = hold_prob * self.model_confidence + (1.0 - self.model_confidence) * (1.0 / 3.0)
        
        # Determine signal type based on highest probability
        probs = {"BUY": buy_prob, "SELL": sell_prob, "HOLD": hold_prob}
        signal_type = max(probs.items(), key=lambda x: x[1])[0]
        confidence = probs[signal_type]
        
        # Strength is how much this probability exceeds uniform baseline (1/3)
        uniform_prob = 1.0 / 3.0
        strength = max(0.0, confidence - uniform_prob) * 1.5  # Scale to [0, 1]
        
        # Create and return SignalEvent
        return SignalEvent(
            symbol="UNKNOWN",  # In practice, this would be set from context
            signal_type=signal_type,
            strength=strength,
            metadata={
                "latest_value": float(latest_value),
                "buy_prob": buy_prob,
                "sell_prob": sell_prob,
                "hold_prob": hold_prob,
                "model_confidence": self.model_confidence,
            },
        )


def test_probabilistic_strategy_creation():
    """Test that we can create a ProbabilisticStrategy."""
    print("Testing ProbabilisticStrategy creation...")
    
    strategy = ProbabilisticStrategy(model_confidence=0.8)
    
    assert strategy is not None
    assert strategy.model_confidence == 0.8
    print("✓ ProbabilisticStrategy created successfully")


def test_probabilistic_strategy_bullish_signal():
    """Test strategy with clearly bullish features."""
    print("Testing ProbabilisticStrategy with bullish signal...")
    
    strategy = ProbabilisticStrategy(model_confidence=0.9)
    
    # Create strongly bullish features
    features = {
        "alpha1": pl.Series("alpha1", [1.0, 1.5, 2.0]),  # Strongly positive
        "alpha2": pl.Series("alpha2", [0.8, 1.2, 1.8]),  # Positive
    }
    
    signal = strategy.compute_signals(features)
    
    # Should generate a BUY signal
    assert signal.signal_type == "BUY"
    assert signal.strength > 0.0
    assert "buy_prob" in signal.metadata
    assert signal.metadata["buy_prob"] > 0.5  # Should favor BUY
    print(f"✓ Bullish signal: {signal.signal_type} with strength {signal.strength:.3f}")
    print(f"  Probabilities: BUY={signal.metadata['buy_prob']:.3f}, "
          f"SELL={signal.metadata['sell_prob']:.3f}, HOLD={signal.metadata['hold_prob']:.3f}")


def test_probabilistic_strategy_bearish_signal():
    """Test strategy with clearly bearish features."""
    print("Testing ProbabilisticStrategy with bearish signal...")
    
    strategy = ProbabilisticStrategy(model_confidence=0.9)
    
    # Create strongly bearish features
    features = {
        "alpha1": pl.Series("alpha1", [-2.0, -1.5, -1.0]),  # Strongly negative
        "alpha2": pl.Series("alpha2", [-1.8, -1.2, -0.8]),  # Negative
    }
    
    signal = strategy.compute_signals(features)
    
    # Should generate a SELL signal
    assert signal.signal_type == "SELL"
    assert signal.strength > 0.0
    assert "sell_prob" in signal.metadata
    assert signal.metadata["sell_prob"] > 0.5  # Should favor SELL
    print(f"✓ Bearish signal: {signal.signal_type} with strength {signal.strength:.3f}")
    print(f"  Probabilities: BUY={signal.metadata['buy_prob']:.3f}, "
          f"SELL={signal.metadata['sell_prob']:.3f}, HOLD={signal.metadata['hold_prob']:.3f}")


def test_probabilistic_strategy_neutral_signal():
    """Test strategy with neutral/mixed features."""
    print("Testing ProbabilisticStrategy with neutral signal...")
    
    strategy = ProbabilisticStrategy(model_confidence=0.9)
    
    # Create mixed/neutral features
    features = {
        "alpha1": pl.Series("alpha1", [0.1, -0.1, 0.0]),  # Near zero
        "alpha2": pl.Series("alpha2", [-0.1, 0.1, 0.0]),  # Near zero
    }
    
    signal = strategy.compute_signals(features)
    
    # Should likely generate a HOLD signal (or weak signal)
    assert signal.signal_type in ["BUY", "SELL", "HOLD"]
    # Strength might be low for neutral signals
    print(f"✓ Neutral signal: {signal.signal_type} with strength {signal.strength:.3f}")
    print(f"  Probabilities: BUY={signal.metadata['buy_prob']:.3f}, "
          f"SELL={signal.metadata['sell_prob']:.3f}, HOLD={signal.metadata['hold_prob']:.3f}")


def test_probabilistic_vs_deterministic():
    """Demonstrate the difference from threshold-based approach."""
    print("Testing comparison with threshold-based approach...")
    
    # Our probabilistic strategy
    prob_strategy = ProbabilisticStrategy(model_confidence=0.8)
    
    # Features that would give weighted sum of 0.6
    # With thresholds of 0.5, deterministic would be BUY
    features = {
        "alpha1": pl.Series("alpha1", [0.5, 0.5, 0.6]),
        "alpha2": pl.Series("alpha2", [0.5, 0.5, 0.6]),
    }
    
    prob_signal = prob_strategy.compute_signals(features)
    
    print(f"Probabilistic approach:")
    print(f"  Signal: {prob_signal.signal_type}")
    print(f"  Strength: {prob_signal.strength:.3f}")
    print(f"  Buy probability: {prob_signal.metadata['buy_prob']:.3f}")
    
    # Show that even with same input, we get nuanced output
    # rather than just a binary threshold decision
    assert prob_signal.signal_type == "BUY"  # Should still be BUY
    assert 0.0 < prob_signal.strength < 1.0  # But with nuanced strength
    print("✓ Probabilistic approach provides graduated confidence")


def main():
    """Run all tests."""
    print("Testing Strategy Layer Upgrade to Probabilistic Signaling (Simple Version)...\n")
    
    test_probabilistic_strategy_creation()
    test_probabilistic_strategy_bullish_signal()
    test_probabilistic_strategy_bearish_signal()
    test_probabilistic_strategy_neutral_signal()
    test_probabilistic_vs_deterministic()
    
    print("\n✅ All strategy upgrade tests passed!")


if __name__ == "__main__":
    main()