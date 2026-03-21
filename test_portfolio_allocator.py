#!/usr/bin/env python3
"""
Test script for PortfolioAllocator
"""
import polars as pl
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our new class
from qtrader.risk.portfolio_allocator import PortfolioAllocator

def test_portfolio_allocator():
    print("Testing PortfolioAllocator...")
    
    # Create sample return series for three strategies
    n = 50
    # Strategy 1: steady positive returns
    returns1 = pl.Series([0.001] * n)
    # Strategy 2: volatile returns
    returns2 = pl.Series([0.002, -0.001, 0.0015, -0.0005, 0.003] * (n // 5))
    # Strategy 3: negative returns
    returns3 = pl.Series([-0.0005] * n)
    
    # Truncate to same length
    min_len = min(len(returns1), len(returns2), len(returns3))
    returns1 = returns1[:min_len]
    returns2 = returns2[:min_len]
    returns3 = returns3[:min_len]
    
    strategy_returns = {
        'strat1': returns1,
        'strat2': returns2,
        'strat3': returns3
    }
    
    print('Input return series lengths:', min_len)
    
    # Test equal weight allocation
    allocator_eq = PortfolioAllocator(method='equal_weight', lookback=10)
    weights_eq = allocator_eq.allocate(strategy_returns)
    print('\nEqual weight allocation:')
    for name, series in weights_eq.items():
        print(f'{name}: {series.to_list()[:5]}... (all values: {series.unique().to_list()})')
    
    # Test inverse volatility allocation
    allocator_inv = PortfolioAllocator(method='inverse_volatility', lookback=10)
    weights_inv = allocator_inv.allocate(strategy_returns)
    print('\nInverse volatility allocation:')
    for name, series in weights_inv.items():
        print(f'{name}: {series.to_list()[:5]}... (all values: {series.unique().to_list()})')
    
    # Test equal risk allocation (which is same as inverse vol in this implementation)
    allocator_er = PortfolioAllocator(method='equal_risk', lookback=10)
    weights_er = allocator_er.allocate(strategy_returns)
    print('\nEqual risk allocation:')
    for name, series in weights_er.items():
        print(f'{name}: {series.to_list()[:5]}... (all values: {series.unique().to_list()})')
    
    # Verify that weights sum to approximately 1.0 for each time point
    for alloc_name, alloc in [('equal_weight', weights_eq), ('inverse_volatility', weights_inv), ('equal_risk', weights_er)]:
        print(f'\n{alloc_name} weight sum check:')
        # Sum the weights for each time point
        # Since each weight series is constant, we can just sum the constants
        total_weight = sum(series[0] for series in alloc.values())  # All values in the series are the same
        print(f'  Total weight: {total_weight:.6f}')
        assert abs(total_weight - 1.0) < 1e-9, f"Weights do not sum to 1.0 for {alloc_name}"
    
    # Test with min and max weight constraints
    allocator_constrained = PortfolioAllocator(
        method='equal_weight', 
        lookback=10, 
        min_weight=0.1, 
        max_weight=0.5
    )
    weights_con = allocator_constrained.allocate(strategy_returns)
    print('\nConstrained equal weight (min=0.1, max=0.5):')
    for name, series in weights_con.items():
        w = series[0]
        print(f'{name}: {w}')
        assert 0.1 <= w <= 0.5, f"Weight for {name} is out of bounds: {w}"
    
    print('\nPortfolioAllocator test passed!')

if __name__ == '__main__':
    test_portfolio_allocator()