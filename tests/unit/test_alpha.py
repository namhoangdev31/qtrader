#!/usr/bin/env python3
"""
Test script for Alpha base class and MomentumAlpha
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new classes directly
from qtrader.strategy.alpha_base import Alpha
from qtrader.strategy.momentum_alpha import MomentumAlpha

def test_alpha_base():
    print("Testing Alpha base class and MomentumAlpha...")
    
    # Create a sample DataFrame with OHLCV data
    df = pl.DataFrame({
        'open': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
        'high': [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
        'low': [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        'close': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
        'volume': [1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0, 1600.0]
    })
    
    print('Input DataFrame:')
    print(df)
    
    # Test MomentumAlpha
    alpha = MomentumAlpha(lookback=3)
    result = alpha.compute(df)
    print('\nMomentumAlpha result:')
    print(result)
    print('\nResult type:', type(result))
    print('Result length:', len(result))
    print('Result dtype:', result.dtype)
    
    # Verify it's a Float64 series
    assert isinstance(result, pl.Series), "Result should be a pl.Series"
    assert result.dtype == pl.Float64, f"Result dtype should be Float64, got {result.dtype}"
    assert len(result) == len(df), f"Result length should match input length: {len(result)} vs {len(df)}"
    
    # Test with missing columns
    df_missing = df.select(['open', 'high', 'low', 'close'])  # missing volume
    result_missing = alpha.compute(df_missing)
    print('\nResult with missing volume column:')
    print(result_missing)
    # Should return neutral fallback (zeros)
    assert all(result_missing == 0.0), "Fallback should be all zeros when columns missing"
    
    print('\nAll tests passed!')

if __name__ == '__main__':
    test_alpha_base()