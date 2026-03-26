"""Exposure decomposition for factors and sectors."""

from __future__ import annotations

import numpy as np


def factor_exposure(
    weights: np.ndarray,
    factor_loadings: np.ndarray,
    factor_names: list[str] | None = None,
) -> dict[str, float]:
    """
    Compute factor exposure of a portfolio.

    Args:
        weights: Portfolio weights (n_assets,).
        factor_loadings: Factor loading matrix (n_assets x n_factors).
        factor_names: Optional list of factor names (length n_factors).
                      If not provided, factors are named "factor_0", "factor_1", etc.

    Returns:
        Dictionary mapping factor name to exposure (scalar).
        Exposure = factor_loadings.T @ weights

    Example:
        >>> w = np.array([0.5, 0.3, 0.2])
        >>> F = np.array([[1, 0], [0, 1], [1, 1]])  # 3 assets, 2 factors
        >>> factor_exposure(w, F, ["beta", "momentum"])
        {'beta': 0.7, 'momentum': 0.5}
    """
    if weights.ndim != 1:
        raise ValueError("weights must be a 1D array")
    if factor_loadings.ndim != 2:
        raise ValueError("factor_loadings must be a 2D array")
    if weights.shape[0] != factor_loadings.shape[0]:
        raise ValueError("Number of assets in weights and factor_loadings must match")

    n_factors = factor_loadings.shape[1]
    if factor_names is None:
        factor_names = [f"factor_{i}" for i in range(n_factors)]
    elif len(factor_names) != n_factors:
        raise ValueError("Length of factor_names must match number of factors")

    # Compute exposures: F.T @ w
    exposures = factor_loadings.T @ weights  # Shape: (n_factors,)

    # Create dictionary mapping factor name to exposure
    return {name: float(exposure) for name, exposure in zip(factor_names, exposures)}


def sector_exposure(
    weights: np.ndarray,
    sector_mapping: np.ndarray,
) -> dict[str, float]:
    """
    Compute sector exposure of a portfolio.

    Args:
        weights: Portfolio weights (n_assets,).
        sector_mapping: Sector assignment for each asset (n_assets,).
                        Each element should be hashable (e.g., string, integer).

    Returns:
        Dictionary mapping sector name to total weight in that sector.

    Example:
        >>> w = np.array([0.5, 0.3, 0.2])
        >>> sectors = np.array(["tech", "tech", "finance"])
        >>> sector_exposure(w, sectors)
        {'tech': 0.8, 'finance': 0.2}
    """
    if weights.ndim != 1:
        raise ValueError("weights must be a 1D array")
    if sector_mapping.ndim != 1:
        raise ValueError("sector_mapping must be a 1D array")
    if weights.shape[0] != sector_mapping.shape[0]:
        raise ValueError("Number of assets in weights and sector_mapping must match")

    # Initialize dictionary for sector exposures
    exposures: dict[str, float] = {}

    # Iterate over assets and accumulate weights by sector
    for weight, sector in zip(weights, sector_mapping):
        # Convert sector to string to ensure dict key is string
        sector_str = str(sector)
        exposures[sector_str] = exposures.get(sector_str, 0.0) + float(weight)

    return exposures
