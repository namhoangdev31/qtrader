"""Unit tests for risk parity allocator."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from qtrader.portfolio.risk_parity import RiskParityAllocator


def test_risk_parity_equal_vol() -> None:
    """Test risk parity with equal volatility assets."""
    # Create returns with equal volatility
    np.random.seed(42)
    T, N = 252, 4  # 1 year daily data, 4 assets
    returns = np.random.normal(0, 0.01, (T, N))  # 1% daily vol for all
    returns_df = pl.DataFrame(returns, schema=[f"asset_{i}" for i in range(N)])

    allocator = RiskParityAllocator()
    weights = allocator.allocate(returns=returns_df)

    # Should be approximately equal weights
    expected = np.array([0.25, 0.25, 0.25, 0.25])
    assert np.allclose(weights, expected, atol=0.05)

    # Weights should sum to 1
    assert np.isclose(np.sum(weights), 1.0)

    # All weights should be positive
    assert np.all(weights > 0)


def test_risk_parity_skewed_vol() -> None:
    """Test risk parity with different volatilities."""
    # Create a diagonal covariance matrix with different volatilities
    # Asset 0: low vol (0.5% -> variance 0.000025)
    # Asset 1: medium vol (1.5% -> variance 0.000225)
    # Asset 2: high vol (2.5% -> variance 0.000625)
    covariance = np.array([[0.000025, 0.0, 0.0], [0.0, 0.000225, 0.0], [0.0, 0.0, 0.000625]])

    allocator = RiskParityAllocator()
    weights = allocator.allocate(covariance=covariance)

    # Debug: print weights and expected
    print(f"DEBUG: Got weights: {weights}")
    print(f"DEBUG: Sum of weights: {np.sum(weights)}")

    # Higher volatility assets should get lower weights
    # Risk parity: w_i ∝ 1/vol_i (since uncorrelated)
    # Volatilities: sqrt(diag) = [0.005, 0.015, 0.025]
    # Weights proportional to 1/vol: [200, 66.6667, 40]
    # Normalized: [0.6667, 0.2222, 0.1111]
    expected_weights = np.array([200, 200 / 3, 40]) / (200 + 200 / 3 + 40)
    print(f"DEBUG: Expected weights: {expected_weights}")
    print(f"DEBUG: Difference: {weights - expected_weights}")

    # Check weights are close to expected (within 1% due to numerical precision)
    assert np.allclose(weights, expected_weights, rtol=0.01), (
        f"Weights {weights} not close to expected {expected_weights}"
    )

    # Weights should sum to 1
    assert np.isclose(np.sum(weights), 1.0)

    # All weights should be positive
    assert np.all(weights > 0)

    # Additionally, verify that risk contributions are approximately equal
    port_var = weights @ covariance @ weights
    port_vol = np.sqrt(port_var)
    mcr = covariance @ weights  # Marginal risk contribution
    rc = weights * mcr  # Risk contribution
    # Risk contributions should be equal (since we solved for risk parity)
    assert np.allclose(rc, rc[0], rtol=0.01), f"Risk contributions not equal: {rc}"


def test_risk_parity_with_covariance() -> None:
    """Test risk parity with precomputed covariance matrix."""
    # Simple 2-asset case with known covariance
    covariance = np.array(
        [
            [0.04, 0.01],  # Asset 0: vol=20%, covariance with asset 1
            [0.01, 0.09],  # Asset 1: vol=30%
        ]
    )

    allocator = RiskParityAllocator()
    weights = allocator.allocate(covariance=covariance)

    # For 2-asset risk parity:
    # w1/w2 = σ2/σ1 * sqrt((1-ρ)/(1-ρ)) = σ2/σ1 when only variance matters
    # More precisely, we solve: w1^2*σ1^2 = w2^2*σ2^2
    # So w1/w2 = σ2/σ1 = 0.3/0.2 = 1.5
    # With w1 + w2 = 1: w1 = 1.5/2.5 = 0.6, w2 = 0.4

    # Check that risk contributions are approximately equal
    port_var = weights @ covariance @ weights
    port_vol = np.sqrt(port_var)
    mcr = covariance @ weights  # Marginal risk contribution
    rc = weights * mcr  # Risk contribution

    # Risk contributions should be equal
    assert np.isclose(rc[0], rc[1], rtol=0.05)

    # Weights should sum to 1
    assert np.isclose(np.sum(weights), 1.0)

    # All weights should be positive
    assert np.all(weights > 0)


def test_risk_parity_single_asset() -> None:
    """Test risk parity with single asset."""
    covariance = np.array([[0.04]])  # 20% volatility

    allocator = RiskParityAllocator()
    weights = allocator.allocate(covariance=covariance)

    # Should be fully invested in the single asset
    assert np.isclose(weights[0], 1.0)
    assert np.isclose(np.sum(weights), 1.0)


def test_risk_parity_optimization_converges() -> None:
    """Test that optimization converges for challenging cases."""
    # Create a covariance matrix that might be challenging
    np.random.seed(42)
    N = 5
    # Generate random correlation matrix
    A = np.random.randn(N, N)
    cov = A @ A.T
    # Make it positive definite
    cov += np.eye(N) * 0.1

    allocator = RiskParityAllocator(max_iterations=50)
    weights = allocator.allocate(covariance=cov)

    # Should produce valid weights
    assert len(weights) == N
    assert np.isclose(np.sum(weights), 1.0)
    assert np.all(weights >= -1e-10)  # Allow tiny numerical negatives
    assert np.all(weights <= 1.0 + 1e-10)


def test_risk_parity_deterministic() -> None:
    """Test that the allocator is deterministic."""
    np.random.seed(123)
    returns = np.random.normal(0, 0.01, (100, 3))
    returns_df = pl.DataFrame(returns, schema=["A", "B", "C"])

    allocator1 = RiskParityAllocator()
    allocator2 = RiskParityAllocator()

    weights1 = allocator1.allocate(returns=returns_df)
    weights2 = allocator2.allocate(returns=returns_df)

    # Should be identical
    assert np.allclose(weights1, weights2)


def test_risk_parity_caching() -> None:
    """Test that caching works when covariance doesn't change."""
    covariance = np.array([[0.04, 0.01], [0.01, 0.09]])

    allocator = RiskParityAllocator()

    # First call
    weights1 = allocator.allocate(covariance=covariance)

    # Second call with same covariance should use cache
    weights2 = allocator.allocate(covariance=covariance)

    # Should be identical (same object due to caching or same values)
    assert np.allclose(weights1, weights2)

    # Different covariance should produce different result
    different_cov = np.array([[0.09, 0.02], [0.02, 0.04]])
    weights3 = allocator.allocate(covariance=different_cov)
    assert not np.allclose(weights1, weights3, atol=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
