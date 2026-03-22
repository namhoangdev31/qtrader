#!/usr/bin/env python3
"""
Test script for Strategy layer - direct import to avoid package issues
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new classes directly from the module files
from qtrader.strategy.alpha_base import Alpha
from qtrader.strategy.momentum_alpha import MomentumAlpha
from qtrader.strategy.strategy_layer import RuleBasedStrategy

def test_strategy_layer():
    print("Testing Strategy layer implementation...")
    
    # Create sample OHLCV data
    df = pl.DataFrame({
        'open': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
        'high': [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        'low': [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
        'close': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 110.0],  # Last jump to create signal
        'volume': [1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0, 1600.0, 1700.0, 1800.0, 1900.0]
    })
    
    print('Input DataFrame:')
    print(df)
    
    # Create alpha feature
    alpha = MomentumAlpha(lookback=3)
    momentum_feature = alpha.compute(df)
    print('\nMomentum feature:')
    print(momentum_feature)
    
    # Create features dictionary
    features = {
        'momentum': momentum_feature
    }
    
    # Create strategy
    strategy = RuleBasedStrategy(
        alpha_weights={'momentum': 1.0},
        buy_threshold=0.5,
        sell_threshold=0.5
    )
    
    # Compute signal
    signal_event = strategy.compute_signals(features)
    print('\nGenerated SignalEvent:')
    print(f"Symbol: {signal_event.symbol}")
    print(f"Signal Type: {signal_event.signal_type}")
    print(f"Strength: {signal_event.strength}")
    print(f"Metadata: {signal_event.metadata}")
    
    # Validate signal type
    assert signal_event.signal_type in ["BUY", "SELL", "HOLD"], f"Invalid signal type: {signal_event.signal_type}"
    
    print('\nStrategy layer test passed!')

if __name__ == '__main__':
    test_strategy_layer()