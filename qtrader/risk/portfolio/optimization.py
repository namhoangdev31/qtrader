from typing import Protocol, runtime_checkable

import numpy as np
import polars as pl
from scipy.optimize import minimize


@runtime_checkable
class PortfolioOptimizer(Protocol):
    """Protocol for portfolio weight optimization."""

    def optimize(
        self, 
        returns: pl.DataFrame, 
        expected_returns: pl.Series | None = None
    ) -> dict[str, float]:
        ...


class MeanVarianceOptimizer(PortfolioOptimizer):
    """Classic Markowitz Mean-Variance Optimization."""

    def __init__(self, risk_aversion: float = 1.0) -> None:
        self.risk_aversion = risk_aversion

    def optimize(
        self, 
        returns: pl.DataFrame, 
        expected_returns: pl.Series | None = None
    ) -> dict[str, float]:
        symbols = returns.columns
        n = len(symbols)
        
        # Calculate covariance matrix
        cov_matrix = returns.to_pandas().cov().values
        
        # If no expected returns provided, use historical mean
        if expected_returns is None:
            er = returns.mean().to_numpy().flatten()
        else:
            er = expected_returns.to_numpy()

        # Objective: Maximize ER - 0.5 * risk_aversion * Variance
        def objective(weights: np.ndarray) -> float:
            port_return = np.dot(weights, er)
            port_var = np.dot(weights.T, np.dot(cov_matrix, weights))
            return -(port_return - 0.5 * self.risk_aversion * port_var)

        # Constraints: sum(weights) == 1, weights >= 0 (long-only)
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0, 1) for _ in range(n))
        
        initial_weights = np.array([1.0 / n] * n)
        
        result = minimize(
            objective, 
            initial_weights, 
            method='SLSQP', 
            bounds=bounds, 
            constraints=constraints
        )
        
        return dict(zip(symbols, result.x, strict=False))
