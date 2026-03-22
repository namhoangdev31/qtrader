#!/usr/bin/env python3
"""
Simple test of risk parity allocation concepts.
"""

from __future__ import annotations

import polars as pl

from qtrader.risk.portfolio_allocator import PortfolioAllocator
from qtrader.risk.portfolio_allocator_enhanced import EnhancedPortfolioAllocator


def test_basic_vs_enhanced_allocator():
    """Test that both allocators work and produce reasonable weights."""
    print("Testing Basic vs Enhanced Allocator...")
    
    # Create simple returns data
    returns_dict = {
        "Strategy_A": pl.Series("a", [0.01, 0.02, -0.01, 0.03]),
        "Strategy_B": pl.Series("b", [-0.01, 0.01, 0.02, -0.02]),
        "Strategy_C": pl.Series("c", [0.005, -0.005, 0.01, -0.01])
    }
    
    # Test basic allocator
    basic_allocator = PortfolioAllocator(method="equal_risk", lookback=2)
    basic_weights = basic_allocator.allocate(returns_dict)
    
    # Test enhanced allocator
    enhanced_allocator = EnhancedPortfolioAllocator(lookback=2)
    enhanced_weights = enhanced_allocator.allocate(returns_dict)
    
    print("Basic Allocator Weights:")
    for name, weight_series in basic_weights.items():
        # Extract the weight value (series of constant weights)
        weight_val = float(weight_series[0])
        print(f"  {name}: {weight_val:.3f}")
    
    print("\nEnhanced Allocator Weights:")
    for name, weight_series in enhanced_weights.items():
        weight_val = float(weight_series[0])
        print(f"  {name}: {weight_val:.3f}")
    
    # Verify weights sum to approximately 1
    basic_sum = sum(float(ws[0]) for ws in basic_weights.values())
    enhanced_sum = sum(float(ws[0]) for ws in enhanced_weights.values())
    
    print(f"\nBasic allocator weight sum: {basic_sum:.3f}")
    print(f"Enhanced allocator weight sum: {enhanced_sum:.3f}")
    
    assert abs(basic_sum - 1.0) < 0.01, "Basic allocator weights should sum to ~1"
    assert abs(enhanced_sum - 1.0) < 0.01, "Enhanced allocator weights should sum to ~1"
    
    print("✓ Both allocators produce valid weight distributions")


def test_constraints():
    """Test that constraints are applied."""
    print("\nTesting Constraint Application...")
    
    allocator = EnhancedPortfolioAllocator(
        min_weight=0.1,
        max_weight=0.6,
        lookback=2
    )
    
    # Create returns where one strategy would dominate without constraints
    returns_dict = {
        "Dominant": pl.Series("dom", [0.05, 0.06, 0.07, 0.08]),  # High returns
        "Weak": pl.Series("weak", [0.001, 0.002, 0.001, 0.002])   # Low returns
    }
    
    weights = allocator.allocate(returns_dict)
    
    print("Weights with constraints (min=0.1, max=0.6):")
    for name, weight_series in weights.items():
        weight_val = float(weight_series[0])
        print(f"  {name}: {weight_val:.3f}")
        
        # Check constraints
        assert weight_val >= 0.1, f"{name} weight below minimum"
        assert weight_val <= 0.6, f"{name} weight above maximum"
    
    total_weight = sum(float(ws[0]) for ws in weights.values())
    print(f"Total weight: {total_weight:.3f}")
    assert abs(total_weight - 1.0) < 0.01, "Weights should sum to ~1"
    
    print("✓ Constraints properly applied")


def main():
    """Run tests."""
    print("Risk Allocator Comparison Test\n")
    
    test_basic_vs_enhanced_allocator()
    test_constraints()
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    main()