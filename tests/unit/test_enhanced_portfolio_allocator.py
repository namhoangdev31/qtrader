#!/usr/bin/env python3
"""
Test script for Enhanced Portfolio Allocator implementation.
"""

from __future__ import annotations

import polars as pl

from qtrader.risk.portfolio_allocator_enhanced import EnhancedPortfolioAllocator, create_enhanced_portfolio_allocator


def test_enhanced_allocator_creation():
    """Test that we can create an EnhancedPortfolioAllocator."""
    print("Testing EnhancedPortfolioAllocator creation...")
    
    allocator = EnhancedPortfolioAllocator()
    
    assert allocator is not None
    assert allocator.target_volatility == 0.15
    assert allocator.lookback == 60
    print("✓ EnhancedPortfolioAllocator created successfully")


def test_enhanced_allocator_custom_params():
    """Test EnhancedPortfolioAllocator with custom parameters."""
    print("Testing EnhancedPortfolioAllocator with custom parameters...")
    
    allocator = EnhancedPortfolioAllocator(
        target_volatility=0.10,
        lookback=30,
        min_weight=0.05,
        max_weight=0.4,
        max_turnover=0.1,
        max_concentration=0.25
    )
    
    assert allocator.target_volatility == 0.10
    assert allocator.lookback == 30
    assert allocator.min_weight == 0.05
    assert allocator.max_weight == 0.4
    assert allocator.max_turnover == 0.1
    assert allocator.max_concentration == 0.25
    print("✓ EnhancedPortfolioAllocator custom parameters work correctly")


def test_enhanced_allocator_empty_returns():
    """Test EnhancedPortfolioAllocator with empty returns."""
    print("Testing EnhancedPortfolioAllocator with empty returns...")
    
    allocator = EnhancedPortfolioAllocator()
    
    # Test with empty returns dict
    result = allocator.allocate({})
    
    # Should return empty dict
    assert result == {}
    print("✓ EnhancedPortfolioAllocator handles empty returns correctly")


def test_enhanced_allocator_single_strategy():
    """Test EnhancedPortfolioAllocator with single strategy."""
    print("Testing EnhancedPortfolioAllocator with single strategy...")
    
    allocator = EnhancedPortfolioAllocator()
    
    # Create returns for single strategy
    returns = {
        "strategy1": pl.Series("returns", [0.01, 0.02, -0.01, 0.03])
    }
    
    # Allocate capital
    weights = allocator.allocate(returns)
    
    # Should allocate 100% to the single strategy
    assert "strategy1" in weights
    assert abs(weights["strategy1"] - 1.0) < 1e-10
    print("✓ EnhancedPortfolioAllocator correctly handles single strategy")


def test_enhanced_allocator_two_strategies_uncorrelated():
    """Test EnhancedPortfolioAllocator with two uncorrelated strategies."""
    print("Testing EnhancedPortfolioAllocator with two uncorrelated strategies...")
    
    allocator = EnhancedPortfolioAllocator(
        target_volatility=0.15,
        lookback=10  # Small lookback for test
    )
    
    # Create two uncorrelated strategies
    # Strategy 1: [+, +, -, +]
    # Strategy 2: [-, -, +, -] 
    returns = {
        "strategy_a": pl.Series("returns_a", [0.02, 0.01, -0.01, 0.03]),
        "strategy_b": pl.Series("returns_b", [-0.01, -0.02, 0.02, -0.01])
    }
    
    # Allocate capital
    weights = allocator.allocate(returns)
    
    # Should allocate weights to both strategies
    assert "strategy_a" in weights
    assert "strategy_b" in weights
    
    # Weights should be positive and sum to approximately 1.0
    total_weight = sum(weights.values())
    assert abs(total_weight - 1.0) < 0.01  # Allow small numerical error
    
    # Both weights should be reasonable (not extreme)
    assert 0.1 <= weights["strategy_a"] <= 0.9
    assert 0.1 <= weights["strategy_b"] <= 0.9
    
    print(f"✓ Weights: strategy_a={weights['strategy_a']:.3f}, strategy_b={weights['strategy_b']:.3f}")
    print(f"  Total weight: {total_weight:.3f}")


def test_enhanced_allocator_constraints():
    """Test that constraints are properly applied."""
    print("Testing EnhancedPortfolioAllocator constraints...")
    
    allocator = EnhancedPortfolioAllocator(
        min_weight=0.1,
        max_weight=0.5,
        max_concentration=0.4
    )
    
    # Create returns that would normally give extreme weights
    # Make one strategy much better than others
    returns = {
        "dominant": pl.Series("dom", [0.05, 0.06, 0.04, 0.07]),  # High returns
        "weak1": pl.Series("w1", [0.001, 0.002, 0.001, 0.002]), # Low returns
        "weak2": pl.Series("w2", [-0.001, 0.001, -0.002, 0.001]) # Near zero returns
    }
    
    # Allocate capital
    weights = allocator.allocate(returns)
    
    # Check that constraints are respected
    for name, weight in weights.items():
        assert weight >= allocator.min_weight, f"{name} weight {weight} < min {allocator.min_weight}"
        assert weight <= allocator.max_weight, f"{name} weight {weight} > max {allocator.max_weight}"
        assert weight <= allocator.max_concentration, f"{name} weight {weight} > concentration {allocator.max_concentration}"
    
    # Weights should still sum to approximately 1.0
    total_weight = sum(weights.values())
    assert abs(total_weight - 1.0) < 0.01
    
    print(f"✓ Constraints respected: {weights}")
    print(f"  Total weight: {total_weight:.3f}")


def test_factory_function():
    """Test the factory function."""
    print("Testing factory function...")
    
    allocator = create_enhanced_portfolio_allocator()
    
    assert allocator is not None
    assert isinstance(allocator, EnhancedPortfolioAllocator)
    print("✓ Factory function works correctly")


def main():
    """Run all tests."""
    print("Testing Enhanced Portfolio Allocator...\n")
    
    test_enhanced_allocator_creation()
    test_enhanced_allocator_custom_params()
    test_enhanced_allocator_empty_returns()
    test_enhanced_allocator_single_strategy()
    test_enhanced_allocator_two_strategies_uncorrelated()
    test_enhanced_allocator_constraints()
    test_factory_function()
    
    print("\n✅ All Enhanced Portfolio Allocator tests passed!")


if __name__ == "__main__":
    main()