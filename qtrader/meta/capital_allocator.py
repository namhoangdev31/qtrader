from __future__ import annotations

import logging
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl  # noqa: TC002

_LOG = logging.getLogger("qtrader.meta.capital_allocator")


class CapitalAllocator:
    """
    Principal Portfolio Allocation Engine.

    Objective: Distribute capital across approved strategies under institutional
    risk constraints. Prevents capital concentration using iterative capping
    and penalizes cross-strategy correlation.
    """

    def __init__(
        self,
        max_position_pct: float = 0.05,
        target_capital: float = 1.0,
        convergence_tol: float = 1e-6,
        max_iterations: int = 100,
    ) -> None:
        """
        Initialize the allocation engine constraints.

        Args:
            max_position_pct: Maximum exposure per individual strategy (default 5%).
            target_capital: Total capital multiplier (default 1.0 for 100%).
            convergence_tol: Tolerance for iterative redistribution.
            max_iterations: Safety limit for redistribution loop convergence.
        """
        self._max_pct = max_position_pct
        self._target_capital = target_capital
        self._tol = convergence_tol
        self._max_iter = max_iterations

        # Telemetry
        self._stats = {"hhi_index": 0.0, "total_strategies": 0}

    def allocate(self, scores: list[float], corr_matrix: pl.DataFrame | None = None) -> list[float]:
        """
        Compute the optimal diversification vector w.

        Logic Flow:
        1. Base allocation: w_i = Score_i / Σ Score_j
        2. Risk-adjustment: w_i = w_i * (1 - Corr_i_avg)
        3. Normalization: Σ w_i = 1
        4. Concentration Cap: w_i ≤ 0.05 with redistribution.

        Args:
            scores: List of strategic consensus scores.
            corr_matrix: N x N correlation matrix of the strategy fleet.

        Returns:
            list[float]: The normalized allocation weight vector.
        """
        n = len(scores)
        if n == 0:
            return []
        if sum(scores) <= 0:
            weights = np.ones(n, dtype=np.float64) / n
        else:
            # 1. Base Allocation (Score-weighted)
            weights = np.array(scores, dtype=np.float64) / sum(scores)

        # 2. Correlation Penalty (Risk-Adjusted)
        if corr_matrix is not None and n > 1:
            # Calculate average correlation of each strategy vs entire portfolio
            corr_values = corr_matrix.to_numpy()
            avg_corrs = (np.sum(corr_values, axis=1) - 1.0) / (n - 1)

            # Apply (1 - corr) penalty. clip at 0 to avoid leverage/negative weights
            penalty = np.clip(1.0 - avg_corrs, 0.0, 1.0)
            weights *= penalty

            # Renormalize to ensure Σ w = 1.0 before capping
            weight_sum = np.sum(weights)
            if weight_sum > 1e-9:  # noqa: PLR2004
                weights /= weight_sum
            else:
                weights = np.ones(n, dtype=np.float64) / n

        # 3. Individual Strategy Capping (Iterative Redistribution)
        if n * self._max_pct >= 1.0:
            weights = self._apply_iterative_cap(weights)
        else:
            # Under-utilization scenario (too few strategies for the cap)
            weights = np.minimum(weights, self._max_pct)

        # 4. Global Capital Scaling
        final_weights = weights * self._target_capital

        # 5. Telemetry: HHI Index (Σ w^2) - Measures Concentration Risk
        self._stats["hhi_index"] = float(np.sum(np.square(weights)))
        self._stats["total_strategies"] = n

        _LOG.info(f"ALLOCATED | n={n} | HHI={self._stats['hhi_index']:.4f}")
        return [float(w) for w in final_weights.tolist()]

    def _apply_iterative_cap(self, weights: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """
        Standard portfolio redistribution algorithm to enforce individual caps.
        """
        w = weights.copy()
        for _ in range(self._max_iter):
            over_mask = w > self._max_pct
            if not np.any(over_mask):
                break

            excess = np.sum(w[over_mask] - self._max_pct)
            w[over_mask] = self._max_pct

            under_mask = w < self._max_pct
            if not np.any(under_mask):
                break

            under_sum = np.sum(w[under_mask])
            if under_sum > 1e-9:  # noqa: PLR2004
                w[under_mask] += (w[under_mask] / under_sum) * excess
            else:
                w[under_mask] += excess / np.sum(under_mask)

        # Final cleanup for floating point noise
        return w / np.sum(w)

    def get_allocation_report(self) -> dict[str, Any]:
        """
        Generate high-level portfolio diversification metrics.
        """
        hhi = round(self._stats["hhi_index"], 4)
        status = "DIVERSIFIED" if hhi < 0.1 else "CONCENTRATED"  # noqa: PLR2004

        return {
            "status": "ALLOCATED",
            "hhi_index": hhi,
            "concentration_status": status,
            "capital_utilization": 1.0 if self._stats["total_strategies"] > 0 else 0.0,
        }
