"""True risk parity allocator using covariance matrix and convex optimization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize

from qtrader.portfolio.optimizer import AllocatorBase

if TYPE_CHECKING:
    import polars as pl


class RiskParityAllocator(AllocatorBase):
    """
    True risk parity allocator that equalizes risk contributions.

    Mathematical formulation:
    - Portfolio volatility: σ_p = sqrt(wᵀ Σ w)
    - Marginal contribution: MC = Σ w
    - Risk contribution: RC_i = w_i * MC_i
    - Objective: minimize ∑(RC_i - σ_p / N)²
    - Subject to: ∑ w_i = 1, w_i ≥ 0
    """

    def __init__(self, risk_aversion: float = 1.0, max_iterations: int = 100) -> None:
        """
        Initialize the risk parity allocator.

        Args:
            risk_aversion: Risk aversion parameter (not used in basic RP, kept for compatibility)
            max_iterations: Maximum iterations for optimization
        """
        self.risk_aversion = risk_aversion
        self.max_iterations = max_iterations
        self._last_covariance: np.ndarray | None = None
        self._last_weights: np.ndarray | None = None

    def allocate(
        self,
        returns: pl.DataFrame | None = None,
        covariance: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Compute risk parity weights.

        Args:
            returns: Historical returns DataFrame (time x assets).
                    If provided, covariance is computed from this.
            covariance: Precomputed covariance matrix (assets x assets).
                       If provided, returns is ignored.

        Returns:
            Array of portfolio weights that achieve risk parity.

        Raises:
            ValueError: If neither returns nor covariance is provided.
        """
        # Validate inputs
        if covariance is None and returns is None:
            raise ValueError("Either returns or covariance must be provided")

        # Compute covariance matrix if not provided
        if covariance is None:
            if returns is None or returns.is_empty():
                raise ValueError("Returns DataFrame is required when covariance is not provided")
            # Compute covariance matrix from returns
            covariance = returns.to_numpy().T @ returns.to_numpy() / (len(returns) - 1)
            # Add small regularization to ensure positive definiteness
            covariance += np.eye(covariance.shape[0]) * 1e-8

        # Check if we can use cached solution
        if self._last_covariance is not None and np.allclose(
            self._last_covariance, covariance, rtol=1e-10, atol=1e-12
        ):
            if self._last_weights is not None:
                return self._last_weights.copy()

        n_assets = covariance.shape[0]

        # Initial guess: inverse volatility weights (good starting point for risk parity)
        # For correlated assets, this is not exact but usually close
        vol = np.sqrt(np.diag(covariance))
        # Avoid division by zero
        vol = np.maximum(vol, 1e-8)
        w0 = 1.0 / vol
        w0 = w0 / np.sum(w0)  # Normalize to sum to 1

        # Constraints: weights sum to 1
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        # Bounds: weights between 0 and 1 (long-only)
        bounds = tuple((0.0, 1.0) for _ in range(n_assets))

        # Objective function: minimize sum of squared differences in risk contributions
        def objective(w: np.ndarray) -> float:
            # Portfolio variance
            port_var = w @ covariance @ w
            if port_var <= 0:
                return 1e10  # Large penalty for invalid portfolio

            # Marginal contribution to variance
            mcr = covariance @ w  # This is ∂(σ_p²)/∂w

            # Risk contribution: w_i * ∂(σ_p²)/∂w_i
            rc = w * mcr

            # Target risk contribution for each asset (equal)
            # Since σ_p² = ∑ RC_i, for equal RC we want RC_i = σ_p² / n_assets
            target_rc = port_var / n_assets

            # Sum of squared deviations from target
            return float(np.sum((rc - target_rc) ** 2))

        # Optimize
        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": self.max_iterations, "ftol": 1e-12},
        )

        if not result.success:
            # Fallback to equal weights if optimization fails
            weights = w0
        else:
            weights = result.x

        # Ensure weights sum to 1 (numerical stability)
        weights = weights / np.sum(weights)

        # Cache the solution
        self._last_covariance = covariance.copy()
        self._last_weights = weights.copy()

        return weights
