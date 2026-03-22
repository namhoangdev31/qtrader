#!/usr/bin/env python3
"""
Test for research metrics
"""
import polars as pl
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qtrader.research.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio

def test():
    print("Testing metrics...")
    
    # Test data: constant positive returns
    returns = pl.Series([0.001] * 252)  # about 25% annual return
    print("Returns (first 5):", returns.head(5))
    
    # Sharpe ratio
    sr = sharpe_ratio(returns, risk_free=0.0, periods_per_year=252)
    print(f"Sharpe ratio: {sr:.4f}")
    # Expected: (0.001 / 0.0) -> but std is not zero because we have constant returns? 
    # Actually, constant returns have std=0, so we should get 0.0 from our function.
    # Let's adjust: we need non-zero std to test properly.
    
    # Test with some volatility
    returns2 = pl.Series([0.001, 0.002, -0.001, 0.0015, -0.0005] * 50)  # 250 returns
    print("\nReturns with volatility (first 5):", returns2.head(5))
    
    sr2 = sharpe_ratio(returns2, risk_free=0.0, periods_per_year=252)
    print(f"Sharpe ratio (with vol): {sr2:.4f}")
    
    so2 = sortino_ratio(returns2, risk_free=0.0, periods_per_year=252)
    print(f"Sortino ratio (with vol): {so2:.4f}")
    
    mdd2 = max_drawdown(returns2)
    print(f"Max drawdown: {mdd2:.4f}")
    
    cal2 = calmar_ratio(returns2, periods_per_year=252)
    print(f"Calmar ratio: {cal2:.4f}")
    
    # Test edge cases
    empty = pl.Series([], dtype=pl.Float64)
    print(f"\nEmpty series Sharpe: {sharpe_ratio(empty)}")
    print(f"Empty series Max DD: {max_drawdown(empty)}")
    
    # Constant returns (should give zero Sharpe and Sortino because std=0)
    const = pl.Series([0.001] * 100)
    print(f"\nConstant returns Sharpe: {sharpe_ratio(const)}")
    print(f"Constant returns Sortino: {sortino_ratio(const)}")
    
    print("\nAll tests completed.")

if __name__ == "__main__":
    test()