#!/usr/bin/env python3
"""
Simple test for research metrics
"""
import polars as pl
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qtrader.research.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio

def test():
    # Simple returns: 0.1% daily
    returns = pl.Series([0.001] * 100)
    print("Returns:", returns[:5])
    
    sr = sharpe_ratio(returns, risk_free=0.0, periods_per_year=252)
    print(f"Sharpe: {sr}")
    
    so = sortino_ratio(returns, risk_free=0.0, periods_per_year=252)
    print(f"Sortino: {so}")
    
    mdd = max_drawdown(returns)
    print(f"Max Drawdown: {mdd}")
    
    cal = calmar_ratio(returns, periods_per_year=252)
    print(f"Calmar: {cal}")
    
    # Test with negative returns
    neg_returns = pl.Series([-0.001] * 100)
    mdd2 = max_drawdown(neg_returns)
    print(f"Max Drawdown (neg): {mdd2}")
    
    print("Test completed successfully.")

if __name__ == "__main__":
    test()