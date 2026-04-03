"""Portfolio Constraint Solver — Standash §4.5.

Quadratic Programming (QP) / Convex Optimization for portfolio weight allocation.
Uses scipy.optimize.minimize with SLSQP for constrained portfolio optimization.

Objective: Minimize portfolio variance subject to:
- Sum of weights = 1
- Min/max weight constraints per asset
- Target return constraint (optional)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

_LOG = logging.getLogger("qtrader.portfolio.qp_solver")


@dataclass(slots=True)
class QPResult:
    """Result of a QP optimization."""

    weights: np.ndarray
    expected_return: float
    portfolio_variance: float
    portfolio_volatility: float
    sharpe_ratio: float
    success: bool
    message: str
    asset_names: list[str]


class PortfolioQPSolver:
    """Quadratic Programming Portfolio Solver — Standash §4.5.

    Solves the mean-variance optimization problem:
        min  w'Σw  (portfolio variance)
        s.t. Σw_i = 1
             w_min <= w_i <= w_max
             w'R >= target_return (optional)

    Where:
    - w: portfolio weights
    - Σ: covariance matrix
    - R: expected returns
    """

    def __init__(
        self,
        min_weight: float = 0.0,
        max_weight: float = 0.20,
        target_return: float | None = None,
        risk_free_rate: float = 0.02,
    ) -> None:
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.target_return = target_return
        self.risk_free_rate = risk_free_rate

    def optimize(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        asset_names: list[str] | None = None,
    ) -> QPResult:
        """Solve the portfolio optimization problem.

        Args:
            expected_returns: Array of expected returns per asset.
            cov_matrix: Covariance matrix of asset returns.
            asset_names: Optional list of asset names.

        Returns:
            QPResult with optimal weights and metrics.
        """
        n_assets = len(expected_returns)
        if asset_names is None:
            asset_names = [f"asset_{i}" for i in range(n_assets)]

        if len(cov_matrix) != n_assets or cov_matrix.shape[0] != cov_matrix.shape[1]:
            raise ValueError(
                f"Covariance matrix shape {cov_matrix.shape} doesn't match {n_assets} assets"
            )

        try:
            from scipy.optimize import minimize
        except ImportError:
            _LOG.error("scipy not available — falling back to equal-weight allocation")
            weights = np.ones(n_assets) / n_assets
            return self._build_result(
                weights, expected_returns, cov_matrix, asset_names, True, "scipy unavailable"
            )

        # Objective: minimize portfolio variance (w'Σw)
        def objective(w: np.ndarray) -> float:
            return float(w @ cov_matrix @ w)

        # Gradient of objective
        def gradient(w: np.ndarray) -> np.ndarray:
            return 2.0 * cov_matrix @ w

        # Constraints
        constraints: list[dict] = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},  # weights sum to 1
        ]

        if self.target_return is not None:
            constraints.append(
                {"type": "ineq", "fun": lambda w: w @ expected_returns - self.target_return}
            )

        # Bounds: min_weight <= w_i <= max_weight
        bounds = tuple((self.min_weight, self.max_weight) for _ in range(n_assets))

        # Initial guess: equal weight
        w0 = np.ones(n_assets) / n_assets

        result = minimize(
            objective,
            w0,
            method="SLSQP",
            jac=gradient,
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        if not result.success:
            _LOG.warning(f"QP optimization failed: {result.message}. Falling back to equal weight.")
            weights = np.ones(n_assets) / n_assets
        else:
            weights = result.x
            # Normalize to ensure sum = 1
            weights = weights / np.sum(weights)

        return self._build_result(
            weights, expected_returns, cov_matrix, asset_names, result.success, result.message
        )

    def optimize_risk_parity(
        self,
        cov_matrix: np.ndarray,
        asset_names: list[str] | None = None,
    ) -> QPResult:
        """Solve for risk parity allocation.

        Risk parity: each asset contributes equally to portfolio risk.
        """
        n_assets = cov_matrix.shape[0]
        if asset_names is None:
            asset_names = [f"asset_{i}" for i in range(n_assets)]

        try:
            from scipy.optimize import minimize
        except ImportError:
            weights = np.ones(n_assets) / n_assets
            fake_returns = np.zeros(n_assets)
            return self._build_result(
                weights, fake_returns, cov_matrix, asset_names, True, "scipy unavailable"
            )

        # Risk parity: minimize sum of (risk_contribution_i - target)^2
        # where target = portfolio_vol / n_assets
        def risk_parity_objective(w: np.ndarray) -> float:
            port_var = float(w @ cov_matrix @ w)
            port_vol = np.sqrt(port_var)
            marginal_risk = cov_matrix @ w
            risk_contrib = w * marginal_risk
            target_risk = port_vol / n_assets
            return float(np.sum((risk_contrib - target_risk) ** 2))

        bounds = tuple((0.01, 1.0) for _ in range(n_assets))
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        w0 = np.ones(n_assets) / n_assets

        result = minimize(
            risk_parity_objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        weights = result.x / np.sum(result.x) if result.success else w0
        fake_returns = np.zeros(n_assets)
        return self._build_result(
            weights, fake_returns, cov_matrix, asset_names, result.success, result.message
        )

    def _build_result(
        self,
        weights: np.ndarray,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        asset_names: list[str],
        success: bool,
        message: str,
    ) -> QPResult:
        port_return = float(weights @ expected_returns)
        port_var = float(weights @ cov_matrix @ weights)
        port_vol = float(np.sqrt(port_var))
        sharpe = (port_return - self.risk_free_rate) / port_vol if port_vol > 0 else 0.0

        return QPResult(
            weights=weights,
            expected_return=port_return,
            portfolio_variance=port_var,
            portfolio_volatility=port_vol,
            sharpe_ratio=sharpe,
            success=success,
            message=message,
            asset_names=asset_names,
        )
