"""Factor neutralization for portfolio weights."""

from __future__ import annotations

import numpy as np


def neutralize_factor_exposure(
    weights: np.ndarray,
    factor_exposure: np.ndarray | None = None,
) -> np.ndarray:
    """
    Neutralize portfolio factor exposure while minimizing change from original weights.

    Solves:
        min ||w' - w||^2
        s.t. F^T w' = 0   (factor neutrality)
             1^T w' = 1   (full investment)

    Args:
        weights: Original portfolio weights (n_assets,).
        factor_exposure: Factor exposure matrix (n_assets x n_factors).
                         Each column is a factor's exposure to assets.
                         If None or empty, only the budget constraint is applied.

    Returns:
        Adjusted weights (n_assets,) that satisfy the constraints.

    Example:
        >>> w = np.array([0.4, 0.3, 0.2, 0.1])
        >>> F = np.array([[1, 0], [0, 1], [1, 1], [0, 0]])  # 2 factors
        >>> w_neutral = neutralize_factor_exposure(w, F)
        >>> logger.info(f"Factor exposure: {F.T @ w_neutral}")  # Should be [0, 0]
        >>> logger.info(f"Sum: {np.sum(w_neutral)}")  # Should be 1
    """
    n = len(weights)
    if n == 0:
        return weights.copy()

    # If no factor exposure provided, only apply budget constraint
    if factor_exposure is None or factor_exposure.size == 0:
        # Only constraint: sum(w') = 1
        w_sum = np.sum(weights)
        # Avoid division by zero in case of zero weights
        if np.abs(w_sum) < 1e-12:
            # If weights sum to zero, distribute evenly to meet sum=1
            return np.ones(n) / n
        # Adjust weights to sum to 1: w' = w + (1 - sum(w)) / n * 1
        return weights + (1.0 - w_sum) / n * np.ones(n)

    # Ensure factor_exposure is 2D
    if factor_exposure.ndim == 1:
        factor_exposure = factor_exposure.reshape(-1, 1)

    n_factors = factor_exposure.shape[1]

    # Build constraint matrix C: (n_factors + 1) x n
    #   First n_factors rows: factor_exposure.T (each row is a factor's exposure across assets)
    #   Last row: ones (for budget constraint)
    C = np.vstack([factor_exposure.T, np.ones((1, n))])

    # Build constraint vector d: (n_factors + 1,)
    #   First n_factors elements: 0 (neutrality constraints)
    #   Last element: 1 (budget constraint)
    d = np.zeros(n_factors + 1)
    d[-1] = 1.0

    # Compute the adjustment using the formula for projection onto affine set:
    #   w' = w - C.T @ (C @ C.T)^{-1} @ (C @ w - d)

    # Compute C @ C.T: (n_factors+1) x (n_factors+1)
    CTC = C @ C.T

    # Add ridge to CTC for numerical stability
    ridge = 1e-8
    CTC += np.eye(CTC.shape[0], dtype=CTC.dtype) * ridge

    # Compute the right-hand side: C @ w - d
    rhs = C @ weights - d

    # Solve (C @ C.T) * z = (C @ w - d) for z
    z = np.linalg.solve(CTC, rhs)

    # Compute adjusted weights: w' = w - C.T @ z
    weights_adjusted = weights - C.T @ z

    return weights_adjusted
