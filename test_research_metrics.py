#!/usr/bin/env python3
"""
Test script for research metrics
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new functions
from qtrader.research.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio

def test_metrics():
    print("Testing research metrics...")
    
    # Create sample returns: 10% annual return, 20% annual volatility (approx)
    # For simplicity, we'll use a constant positive return series
    returns = pl.Series([0.001] * 252)  # 0.1% daily return ~ 25% annual
    
    print('Input returns (first 5):', returns.head(5))
    
    # Test Sharpe ratio
    sr = sharpe_ratio(returns, risk_free=0.0, periods_per_year=252)
    print(f'\\nSharpe ratio: {sr:.4f}')
    
    # Test Sortino ratio
    sort = sortino_ratio(returns, risk_free=0.0, periods_per_year=252)
    print(f'Sortino ratio: {sort:.4f}')
    
    # Test max drawdown (should be 0 for all positive returns)
    mdd = max_drawdown(returns)
    print(f'Max drawdown: {mdd:.4f}')
    
    # Test Calmar ratio
    cal = calmar_ratio(returns, periods_per_year=252)
    print(f'Calmar ratio: {cal:.4f}')
    
    # Test with a series that has a drawdown
    returns_with_dd = pl.Series([0.01, 0.02, -0.05, 0.03, 0.04])
    mdd2 = max_drawdown(returns_with_dd)
    print(f'\\nMax drawdown for mixed returns: {mdd2:.4f}')
    
    # Verify types and ranges
    assert isinstance(sr, float), "Sharpe ratio should be float"
    assert isinstance(sort, float), "Sortino ratio should be float"
    assert isinstance(mdd, float), "Max drawdown should be float"
    assert isinstance(cal, float), "Calmar ratio should be float"
    assert mdd >= 0, "Max drawdown should be non-negative"
    
    print('\\nAll tests passed!')

if __name__ == '__main__':
    test_metrics()