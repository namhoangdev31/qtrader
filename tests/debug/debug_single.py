#!/usr/bin/env python3

import polars as pl
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy

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

print(f"Signal type: {signal_event.signal_type}")
print(f"Metadata keys: {list(signal_event.metadata.keys())}")
print(f"Metadata: {signal_event.metadata}")

if hasattr(signal_event, 'strength'):
    print(f"Signal strength attribute: {signal_event.strength}")
else:
    print("No strength attribute")