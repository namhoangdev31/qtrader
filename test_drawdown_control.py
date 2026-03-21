#!/usr/bin/env python3
"""
Test script for DrawdownControl
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new class
from qtrader.risk.drawdown_control import DrawdownControl

def test_drawdown_control():
    print("Testing DrawdownControl...")
    
    # Create sample equity curve: starts at 1.0, increases to 1.2, then drops to 0.9, then recovers to 1.0
    equity = [1.0, 1.05, 1.1, 1.15, 1.2, 1.18, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.92, 0.95, 1.0]
    df = pl.DataFrame({
        'equity': equity
    })
    
    print('Input Equity DataFrame:')
    print(df)
    
    # Create DrawdownControl instance with max_dd_threshold=0.2 (20%), soft_limit=0.5*0.2=0.1, hard_limit=0.8*0.2=0.16
    dd_control = DrawdownControl(max_dd_threshold=0.2, soft_limit_pct=0.5, hard_limit_pct=0.8)
    
    # Compute drawdown scaling factor
    dd_scaling = dd_control.compute(df)
    print('\nDrawdown scaling factor:')
    print(dd_scaling)
    print('\\nResult type:', type(dd_scaling))
    print('Result length:', len(dd_scaling))
    print('Result dtype:', dd_scaling.dtype)
    
    # Verify it's a Float64 series
    assert isinstance(dd_scaling, pl.Series), "Result should be a pl.Series"
    assert dd_scaling.dtype == pl.Float64, f"Result dtype should be Float64, got {dd_scaling.dtype}"
    assert len(dd_scaling) == len(df), f"Result length should match input length: {len(dd_scaling)} vs {len(df)}"
    
    # Manual calculation of expected drawdown and scaling factor for a few points:
    # Equity: [1.0, 1.05, 1.1, 1.15, 1.2, 1.18, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.92, 0.95, 1.0]
    # Running max: [1.0, 1.05, 1.1, 1.15, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2]
    # Drawdown: (running_max - equity) / running_max
    #   [0.0, 0.0, 0.0, 0.0, 0.0, 0.0167, 0.0417, 0.1667, 0.125, 0.1667, 0.2083, 0.25, 0.2333, 0.2083, 0.1667]
    # With soft_limit=0.1, hard_limit=0.16:
    #   When drawdown <= 0.1 -> scaling = 1.0
    #   When drawdown >= 0.16 -> scaling = 0.0
    #   Between 0.1 and 0.16: scaling = (0.16 - drawdown) / (0.16 - 0.1) = (0.16 - dd) / 0.06
    #
    # Index: 0 dd=0.0 -> 1.0
    # Index: 1 dd=0.0 -> 1.0
    # Index: 2 dd=0.0 -> 1.0
    # Index: 3 dd=0.0 -> 1.0
    # Index: 4 dd=0.0 -> 1.0
    # Index: 5 dd=0.0167 -> (0.16-0.0167)/0.06 = 0.1433/0.06 = 2.388 -> but wait, this is above soft_limit? Actually 0.0167 < 0.1 -> should be 1.0
    # Let's recalculate: 
    #   Actually, the drawdown at index 5 is (1.2 - 1.18)/1.2 = 0.02/1.2 = 0.0167 -> which is less than 0.1 -> scaling=1.0
    # Index: 6 dd=0.0417 -> (1.2-1.15)/1.2=0.05/1.2=0.0417 <0.1 -> scaling=1.0
    # Index: 7 dd=0.125 -> (1.2-1.1)/1.2=0.1/1.2=0.0833? Wait, let's do: equity[7]=1.1, running_max[7]=1.2 -> (1.2-1.1)/1.2=0.1/1.2=0.08333 -> still <0.1 -> scaling=1.0
    # Index: 8 dd=0.125 -> equity[8]=1.05, (1.2-1.05)/1.2=0.15/1.2=0.125 -> between 0.1 and 0.16 -> scaling=(0.16-0.125)/0.06=0.035/0.06=0.5833
    # Index: 9 dd=0.1667 -> equity[9]=1.0, (1.2-1.0)/1.2=0.2/1.2=0.1667 -> >=0.16 -> scaling=0.0
    # Index:10 dd=0.2083 -> equity[10]=0.95, (1.2-0.95)/1.2=0.25/1.2=0.2083 -> >=0.16 -> scaling=0.0
    # Index:11 dd=0.25 -> equity[11]=0.9, (1.2-0.9)/1.2=0.3/1.2=0.25 -> >=0.16 -> scaling=0.0
    # Index:12 dd=0.2333 -> equity[12]=0.92, (1.2-0.92)/1.2=0.28/1.2=0.2333 -> >=0.16 -> scaling=0.0
    # Index:13 dd=0.2083 -> equity[13]=0.95, (1.2-0.95)/1.2=0.25/1.2=0.2083 -> >=0.16 -> scaling=0.0
    # Index:14 dd=0.1667 -> equity[14]=1.0, (1.2-1.0)/1.2=0.2/1.2=0.1667 -> >=0.16 -> scaling=0.0
    #
    # So expected scaling:
    #   [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5833, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    #
    expected = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5833, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    for i, (exp, got) in enumerate(zip(expected, dd_scaling.to_list())):
        if i < 8 or i >= 9:  # First 8 and last 6 should be exactly 1.0 or 0.0
            assert abs(exp - got) < 1e-9, f"At index {i}: expected {exp}, got {got}"
        else:  # Index 8 is the only middle one
            assert abs(exp - got) < 1e-3, f"At index {i}: expected {exp}, got {got}"
    
    print('\nDrawdownControl test passed!')

if __name__ == '__main__':
    test_drawdown_control()