#!/usr/bin/env python3

import polars as pl
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy

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

print(f"Signal type: {signal_event.signal_type}")
print(f"Metadata keys: {list(signal_event.metadata.keys())}")
print(f"Metadata: {signal_event.metadata}")

if 'strength' in signal_event.metadata:
    print(f"Strength: {signal_event.metadata['strength']}")
else:
    print("No strength in metadata")
    
if hasattr(signal_event, 'strength'):
    print(f"Signal strength attribute: {signal_event.strength}")
else:
    print("No strength attribute")