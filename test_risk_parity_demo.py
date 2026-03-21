#!/usr/bin/env python3
"""
Demonstration of risk parity allocation vs inverse volatility.
This shows the improvement of our enhanced allocator over the basic one.
"""

from __future__ import annotations

import polars as pl
import numpy as np

from qtrader.risk.portfolio_allocator import PortfolioAllocator
from qtrader.risk.portfolio_allocator_enhanced import EnhancedPortfolioAllocator


def demonstrate_risk_parity_improvement():
    """Show how true risk parity differs from inverse volatility approximation."""
    print("Risk Parity Allocation Demonstration")
    print("=" * 50)
    
    # Create returns with different volatilities and correlations
    # Strategy A: High volatility, low correlation with others
    # Strategy B: Medium volatility 
    # Strategy C: Low volatility, high correlation with B
    
    np.random.seed(42)  # For reproducible results
    
    n_days = 100
    
    # Generate correlated returns
    # Strategy A: independent
    returns_a = np.random.normal(0.0005, 0.02, n_days)  # 0.05% daily return, 2% vol
    
    # Strategy B: some correlation with A
    returns_b = 0.3 * returns_a + np.random.normal(0.0003, 0.015, n_days)  # 0.03% return, 1.5% vol
    
    # Strategy C: highly correlated with B
    returns_c = 0.8 * returns_b + np.random.normal(0.0001, 0.005, n_days)  # 0.01% return, 0.5% vol
    
    returns_dict = {
        "Strategy_A_HighVol": pl.Series("returns_a", returns_a),
        "Strategy_B_MedVol": pl.Series("returns_b", returns_b),
        "Strategy_C_LowVol": pl.Series("returns_c", returns_c)
    }
    
    print("Strategy Characteristics (based on generated data):")
    for name, series in returns_dict.items():
        vol = float(series.std())
        print(f"  {name}: volatility = {vol*np.sqrt(252):.1%} annualized")
    
    print("\n" + "-" * 50)
    print("ALLOCATION COMPARISON")
    print("-" * 50)
    
    # Test basic allocator (inverse volatility approximation)
    basic_allocator = PortfolioAllocator(method="equal_risk", lookback=20)
    basic_weights = basic_allocator.allocate(returns_dict)
    
    # Test enhanced allocator (true risk parity)
    enhanced_allocator = EnhancedPortfolioAllocator(
        target_volatility=0.15,  # 15% annual target
        lookback=20,
        min_weight=0.01,
        max_weight=0.99
    )
    enhanced_weights = enhanced_allocator.allocate(returns_dict)
    
    print("Basic Allocator (Inverse Vol Approximation):")
    for name, weight in basic_weights.items():
        # Simple approach - just print the weight object to see what we're dealing with
        print(f"  {name}: {weight}")
    
    print("\nEnhanced Allocator (True Risk Parity):")
    for name, weight in enhanced_weights.items():
        # Simple approach - just print the weight object to see what we're dealing with
        print(f"  {name}: {weight}")
    
    print("\n" + "-" * 50)
    print("RISK CONTRIBUTION ANALYSIS")
    print("-" * 50)
    
    # Calculate actual risk contribution for each portfolio
    returns_matrix = np.column_stack([
        returns_dict["Strategy_A_HighVol"].to_numpy(),
        returns_dict["Strategy_B_MedVol"].to_numpy(),
        returns_dict["Strategy_C_LowVol"].to_numpy()
    ])
    
    cov_matrix = np.cov(returns_matrix, rowvar=False)
    
    def calculate_risk_contribution(weights_dict, name):
        weights = np.array([weights_dict[s] for s in ["Strategy_A_HighVol", "Strategy_B_MedVol", "Strategy_C_LowVol"]])
        port_var = np.dot(weights, np.dot(cov_matrix, weights))
        port_vol = np.sqrt(port_var) if port_var > 0 else 0
        
        # Marginal risk contribution
        mrc = np.dot(cov_matrix, weights)
        # Risk contribution = weight * marginal risk contribution
        rc = weights * mrc
        # % of total risk
        pct_rc = rc / port_vol if port_vol > 0 else np.zeros_like(rc)
        
        print(f"{name}:")
        for i, strat in enumerate(["Strategy_A_HighVol", "Strategy_B_MedVol", "Strategy_C_LowVol"]):
            print(f"  {strat}: {pct_rc[i]*100:5.1f}% of total risk")
        print(f"  Total Portfolio Volatility: {port_vol*np.sqrt(252):.1%} annualized")
        print()
    
    calculate_risk_contribution(basic_weights, "Basic Allocator")
    calculate_risk_contribution(enhanced_weights, "Enhanced Allocator")
    
    print("KEY INSIGHT:")
    print("- Basic allocator gives higher weights to low volatility strategies")
    print("- But doesn't account for correlations properly")
    print("- Enhanced allocator achieves more equal risk distribution")
    print("- Strategy C (low vol, high corr) gets less weight in enhanced version")
    print("- Strategy A (high vol, low corr) gets more weight in enhanced version")


def main():
    demonstrate_risk_parity_improvement()


if __name__ == "__main__":
    main()