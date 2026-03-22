#!/usr/bin/env python3
"""
Test script for PositionSizer
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new classes
from qtrader.risk.volatility import VolatilityTargeting
from qtrader.risk.position_sizer import PositionSizer

def test_position_sizer():
    print("Testing PositionSizer...")
    
    # Create sample OHLCV data
    df = pl.DataFrame({
        'close': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0,
                  110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0]
    })
    
    print('Input DataFrame shape:', df.shape)
    
    # Create VolatilityTargeting instance
    vol_target = VolatilityTargeting(lookback=5, target_vol=0.02, annualize=False)
    
    # Create PositionSizer instance
    position_sizer = PositionSizer(volatility_targeting=vol_target, max_position=1.0)
    
    # Create sample signals: BUY=1, SELL=-1, HOLD=0
    signals = pl.Series([
        0, 0, 0, 0, 0,  # First 5 values (lookback period) - should result in 0 position due to vol scaling
        1, 1, 1, 1, 1,  # BUY signals
        0, 0, 0, 0, 0,  # HOLD signals
        -1, -1, -1, -1, -1  # SELL signals
    ])
    
    print('\\nSignals:')
    print(signals)
    
    # Compute position sizes
    positions = position_sizer.compute(data=df, signals=signals)
    print('\\nPosition sizes:')
    print(positions)
    print('\\nResult type:', type(positions))
    print('Result length:', len(positions))
    print('Result dtype:', positions.dtype)
    
    # Verify it's a Float64 series
    assert isinstance(positions, pl.Series), "Result should be a pl.Series"
    assert positions.dtype == pl.Float64, f"Result dtype should be Float64, got {positions.dtype}"
    assert len(positions) == len(df), f"Result length should match input length: {len(positions)} vs {len(df)}"
    
    # Check that positions are within bounds
    assert all(positions >= -1.0) and all(positions <= 1.0), "Positions should be clipped to [-1, 1]"
    
    # Check that first 5 positions are 0 (due to insufficient data for volatility calculation)
    first_five = positions.head(5)
    print(f'\\nFirst 5 positions (should be 0.0):')
    print(first_five)
    assert all(first_five == 0.0), "First 5 positions should be 0.0"
    
    print('\nPositionSizer test passed!')

if __name__ == '__main__':
    test_position_sizer()