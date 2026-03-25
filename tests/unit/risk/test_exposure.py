"""Unit tests for exposure decomposition."""

from __future__ import annotations

import numpy as np
import pytest

from qtrader.risk.exposure import factor_exposure, sector_exposure


def test_factor_exposure_basic() -> None:
    """Test basic factor exposure calculation."""
    weights = np.array([0.5, 0.3, 0.2])
    factor_loadings = np.array(
        [
            [1, 0],  # Asset 0: factor 0 = 1, factor 1 = 0
            [0, 1],  # Asset 1: factor 0 = 0, factor 1 = 1
            [1, 1],  # Asset 2: factor 0 = 1, factor 1 = 1
        ]
    )

    exposures = factor_exposure(weights, factor_loadings, ["factor_A", "factor_B"])

    # Factor A exposure: 0.5*1 + 0.3*0 + 0.2*1 = 0.5 + 0 + 0.2 = 0.7
    # Factor B exposure: 0.5*0 + 0.3*1 + 0.2*1 = 0 + 0.3 + 0.2 = 0.5
    assert exposures["factor_A"] == 0.7
    assert exposures["factor_B"] == 0.5


def test_factor_exposure_default_names() -> None:
    """Test factor exposure with default factor names."""
    weights = np.array([0.6, 0.4])
    factor_loadings = np.array([[2, 1], [1, 3]])

    exposures = factor_exposure(weights, factor_loadings)  # No factor names provided

    # Should use default names: factor_0, factor_1
    assert "factor_0" in exposures
    assert "factor_1" in exposures

    # Factor 0: 0.6*2 + 0.4*1 = 1.2 + 0.4 = 1.6
    # Factor 1: 0.6*1 + 0.4*3 = 0.6 + 1.2 = 1.8
    assert exposures["factor_0"] == 1.6
    assert abs(exposures["factor_1"] - 1.8) < 1e-10


def test_factor_exposure_zero_weights() -> None:
    """Test factor exposure with zero weights."""
    weights = np.array([0.0, 0.0, 0.0])
    factor_loadings = np.array([[1, 2], [3, 4], [5, 6]])

    exposures = factor_exposure(weights, factor_loadings, ["f1", "f2"])

    assert exposures["f1"] == 0.0
    assert exposures["f2"] == 0.0


def test_factor_exposure_single_asset() -> None:
    """Test factor exposure with single asset."""
    weights = np.array([1.0])
    factor_loadings = np.array([[0.5, 1.5]])

    exposures = factor_exposure(weights, factor_loadings, ["alpha", "beta"])

    assert exposures["alpha"] == 0.5
    assert exposures["beta"] == 1.5


def test_sector_exposure_basic() -> None:
    """Test basic sector exposure calculation."""
    weights = np.array([0.5, 0.3, 0.2])
    sector_mapping = np.array(["tech", "tech", "finance"])

    exposures = sector_exposure(weights, sector_mapping)

    # Tech: 0.5 + 0.3 = 0.8
    # Finance: 0.2
    assert exposures["tech"] == 0.8
    assert exposures["finance"] == 0.2


def test_sector_exposure_multiple_sectors() -> None:
    """Test sector exposure with multiple sectors."""
    weights = np.array([0.1, 0.2, 0.3, 0.4])
    sector_mapping = np.array(["A", "B", "A", "C"])

    exposures = sector_exposure(weights, sector_mapping)

    # Sector A: 0.1 + 0.3 = 0.4
    # Sector B: 0.2
    # Sector C: 0.4
    assert exposures["A"] == 0.4
    assert exposures["B"] == 0.2
    assert exposures["C"] == 0.4


def test_sector_exposure_single_sector() -> None:
    """Test sector exposure with all assets in same sector."""
    weights = np.array([0.2, 0.3, 0.5])
    sector_mapping = np.array(["energy", "energy", "energy"])

    exposures = sector_exposure(weights, sector_mapping)

    assert exposures["energy"] == 1.0  # 0.2 + 0.3 + 0.5 = 1.0


def test_sector_exposure_empty_weights() -> None:
    """Test sector exposure with zero weights."""
    weights = np.array([0.0, 0.0, 0.0])
    sector_mapping = np.array(["A", "B", "C"])

    exposures = sector_exposure(weights, sector_mapping)

    assert exposures["A"] == 0.0
    assert exposures["B"] == 0.0
    assert exposures["C"] == 0.0


def test_factor_exposure_input_validation() -> None:
    """Test input validation for factor exposure."""
    # Wrong weights dimension
    with pytest.raises(ValueError):
        factor_exposure(np.array([[1, 2]]), np.array([[1, 0], [0, 1]]))

    # Wrong factor_loadings dimension
    with pytest.raises(ValueError):
        factor_exposure(np.array([1, 2]), np.array([1, 2, 3]))

    # Mismatched dimensions
    with pytest.raises(ValueError):
        factor_exposure(np.array([1, 2, 3]), np.array([[1, 0], [0, 1]]))  # 3 assets vs 2 rows

    # Wrong factor_names length
    with pytest.raises(ValueError):
        factor_exposure(
            np.array([1, 2]),
            np.array([[1, 0], [0, 1]]),
            ["only_one_name"],  # Should be 2 names for 2 factors
        )


def test_sector_exposure_input_validation() -> None:
    """Test input validation for sector exposure."""
    # Wrong weights dimension
    with pytest.raises(ValueError):
        sector_exposure(np.array([[1, 2]]), np.array(["A", "B"]))

    # Wrong sector_mapping dimension
    with pytest.raises(ValueError):
        sector_exposure(np.array([1, 2]), np.array([["A"], ["B"]]))

    # Mismatched dimensions
    with pytest.raises(ValueError):
        sector_exposure(np.array([1, 2, 3]), np.array(["A", "B"]))  # 3 weights vs 2 sectors


def test_factor_exposure_consistency() -> None:
    """Test that factor exposure is consistent with definition."""
    np.random.seed(42)
    n_assets, n_factors = 5, 3
    weights = np.random.rand(n_assets)
    weights = weights / np.sum(weights)  # Normalize to sum to 1
    factor_loadings = np.random.randn(n_assets, n_factors)
    factor_names = [f"factor_{i}" for i in range(n_factors)]

    exposures = factor_exposure(weights, factor_loadings, factor_names)

    # Manual calculation
    manual_exposures = factor_loadings.T @ weights

    for i, name in enumerate(factor_names):
        assert np.isclose(exposures[name], manual_exposures[i])


def test_sector_exposure_consistency() -> None:
    """Test that sector exposure is consistent with definition."""
    np.random.seed(42)
    n_assets = 6
    weights = np.random.rand(n_assets)
    weights = weights / np.sum(weights)  # Normalize
    sectors = np.array(["tech", "finance", "tech", "healthcare", "finance", "tech"])

    exposures = sector_exposure(weights, sectors)

    # Manual calculation
    manual_exposures = {}
    for weight, sector in zip(weights, sectors):
        sector_str = str(sector)
        manual_exposures[sector_str] = manual_exposures.get(sector_str, 0.0) + weight

    assert exposures == manual_exposures


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
