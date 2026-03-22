#!/usr/bin/env python3
"""
Test script for VolatilityTargeting
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new class
from qtrader.risk.volatility import VolatilityTargeting

def test_volatility_targeting():
    print("Testing VolatilityTargeting...")
    
    # Create sample OHLCV data
    df = pl.DataFrame({
        'close': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    })
    
    print('Input DataFrame:')
    print(df)
    
    # Create VolatilityTargeting instance
    vol_target = VolatilityTargeting(lookback=3, target_vol=0.01, annualize=False)
    
    # Compute volatility scaling factor
    vol_scaling = vol_target.compute(df)
    print('\nVolatility scaling factor:')
    print(vol_scaling)
    print('\\nResult type:', type(vol_scaling))
    print('Result length:', len(vol_scaling))
    print('Result dtype:', vol_scaling.dtype)
    
    # Verify it's a Float64 series
    assert isinstance(vol_scaling, pl.Series), "Result should be a pl.Series"
    assert vol_scaling.dtype == pl.Float64, f"Result dtype should be Float64, got {vol_scaling.dtype}"
    assert len(vol_scaling) == len(df), f"Result length should match input length: {len(vol_scaling)} vs {len(df)}"
    
    # Check that the first (lookback-1) values are 0.0 (due to insufficient data for rolling std)
    # Actually, the first (lookback-1) values of rolling_std are null, then we replace with 0.0 in our expression
    # So the first (lookback-1) values should be 0.0
    expected_zeros = vol_target.lookback - 1
    if expected_zeros > 0:
        first_vals = vol_scaling.head(expected_zeros)
        print(f'\\nFirst {expected_zeros} values (should be 0.0):')
        print(first_vals)
        assert all(first_vals == 0.0), f"First {expected_zeros} values should be 0.0"
    
    print('\nVolatilityTargeting test passed!')

if __name__ == '__main__':
    test_volatility_targeting()