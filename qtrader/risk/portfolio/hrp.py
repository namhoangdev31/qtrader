from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy.cluster.hierarchy import leaves_list, linkage, optimal_leaf_ordering
from scipy.optimize import linprog
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

__all__ = ["CVaROptimizer", "HRPOptimizer"]


@dataclass(slots=True)
class HRPOptimizer:
    """Hierarchical Risk Parity. Lopez de Prado (2016).

    Uses Ledoit-Wolf shrinkage for the covariance matrix and the classic
    HRP clustering + recursive bisection algorithm to produce long-only
    portfolio weights that sum to one.
    """

    def optimize(self, returns: pl.DataFrame) -> dict[str, float]:
        """Compute HRP portfolio weights.

        Args:
            returns: T×N matrix of asset returns, columns are symbols.

        Returns:
            Dictionary of symbol to weight, summing to one.
        """
        if returns.height == 0 or len(returns.columns) == 0:
            return {}

        symbols = list(returns.columns)
        if len(symbols) == 1:
            return {symbols[0]: 1.0}

        x = returns.to_numpy()
        cov_est = LedoitWolf().fit(x)
        cov: np.ndarray = cov_est.covariance_
        corr: np.ndarray = cov_est.covariance_ / np.sqrt(
            np.outer(np.diag(cov_est.covariance_), np.diag(cov_est.covariance_)),
        )

        dist = np.sqrt(0.5 * (1.0 - corr))
        condensed = squareform(dist, checks=False)
        link = linkage(condensed, method="single")
        ordered_link = optimal_leaf_ordering(link, condensed)
        order = leaves_list(ordered_link)

        cov_ord = cov[np.ix_(order, order)]
        weights_ord = self._recursive_bisection(cov_ord)

        weights = np.zeros_like(weights_ord)
        for idx, w in zip(order, weights_ord):
            weights[idx] = w

        weights = np.clip(weights, 0.0, None)
        total = float(weights.sum())
        if total == 0.0:
            weights = np.full_like(weights, 1.0 / float(len(weights)))
        else:
            weights /= total

        assert abs(float(weights.sum()) - 1.0) < 1e-6
        return {symbol: float(weights[i]) for i, symbol in enumerate(symbols)}

    def _recursive_bisection(self, cov: np.ndarray) -> np.ndarray:
        """Perform HRP recursive bisection on an ordered covariance matrix."""
        n = cov.shape[0]
        weights = np.ones(n, dtype=float)
        clusters = [(0, n)]

        while clusters:
            start, end = clusters.pop(0)
            if end - start <= 1:
                continue

            mid = start + (end - start) // 2
            left = (start, mid)
            right = (mid, end)

            c_left = cov[start:mid, start:mid]
            c_right = cov[mid:end, mid:end]

            w_left = self._inverse_variance_portfolio(c_left)
            w_right = self._inverse_variance_portfolio(c_right)

            var_left = float(w_left.T @ c_left @ w_left)
            var_right = float(w_right.T @ c_right @ w_right)

            alpha_left = 1.0 - var_left / (var_left + var_right)
            alpha_right = 1.0 - alpha_left

            weights[start:mid] *= alpha_left
            weights[mid:end] *= alpha_right

            clusters.append(left)
            clusters.append(right)

        return weights

    @staticmethod
    def _inverse_variance_portfolio(cov: np.ndarray) -> np.ndarray:
        """Compute inverse-variance weights within a covariance submatrix."""
        inv_var = 1.0 / np.diag(cov)
        inv_var = np.clip(inv_var, 0.0, None)
        total = float(inv_var.sum())
        if total == 0.0:
            return np.full_like(inv_var, 1.0 / float(len(inv_var)))
        return inv_var / total


@dataclass(slots=True)
class CVaROptimizer:
    """CVaR minimization via Rockafellar-Uryasev LP (2000)."""

    alpha: float = 0.05
    long_only: bool = True

    def optimize(self, returns: pl.DataFrame) -> dict[str, float]:
        """Compute CVaR-minimising portfolio weights via linear programming.

        Args:
            returns: T×N matrix of asset returns, columns are symbols.

        Returns:
            Dictionary of symbol to weight, summing to one.
        """
        if returns.height == 0 or len(returns.columns) == 0:
            return {}

        symbols = list(returns.columns)
        r = returns.to_numpy()
        t, n = r.shape

        # Decision vars: w (n), VaR (1), z (t)
        num_vars = n + 1 + t
        idx_var = n
        idx_z_start = n + 1

        c = np.zeros(num_vars, dtype=float)
        c[idx_var] = 1.0
        c[idx_z_start:] = 1.0 / ((1.0 - self.alpha) * float(t))

        # Inequalities: z_t >= -r_t^T w - VaR, and z_t >= 0.
        a_ub = []
        b_ub = []

        for i in range(t):
            row = np.zeros(num_vars, dtype=float)
            row[:n] = -r[i]
            row[idx_var] = -1.0
            row[idx_z_start + i] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)

        A_ub = np.vstack(a_ub)
        b_ub_arr = np.array(b_ub, dtype=float)

        # Equality: sum(w) = 1
        A_eq = np.zeros((1, num_vars), dtype=float)
        A_eq[0, :n] = 1.0
        b_eq = np.array([1.0], dtype=float)

        bounds = []
        for _ in range(n):
            if self.long_only:
                bounds.append((0.0, 1.0))
            else:
                bounds.append((None, None))
        bounds.append((None, None))
        bounds.extend((0.0, None) for _ in range(t))

        result = linprog(
            c,
            A_ub=A_ub,
            b_ub=b_ub_arr,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
        )
        if not result.success:
            weights = np.full(n, 1.0 / float(n))
        else:
            w = result.x[:n]
            if self.long_only:
                w = np.clip(w, 0.0, None)
            total = float(w.sum())
            weights = w / total if total > 0.0 else np.full(n, 1.0 / float(n))

        assert abs(float(weights.sum()) - 1.0) < 1e-6
        if self.long_only:
            assert np.all(weights >= -1e-8)

        return {symbol: float(weights[i]) for i, symbol in enumerate(symbols)}


"""
Pytest-style examples (conceptual):

def test_hrp_weights_sum_to_one() -> None:
    import polars as pl

    returns = pl.DataFrame(
        {
            "A": [0.01, -0.02, 0.015],
            "B": [0.011, -0.019, 0.016],
        },
    )
    hrp = HRPOptimizer()
    weights = hrp.optimize(returns)
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_cvar_long_only_non_negative() -> None:
    import polars as pl

    returns = pl.DataFrame(
        {
            "A": [0.01, -0.02, 0.015],
            "B": [0.02, -0.01, 0.01],
        },
    )
    opt = CVaROptimizer(alpha=0.05, long_only=True)
    weights = opt.optimize(returns)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert all(w >= 0.0 for w in weights.values())
"""

