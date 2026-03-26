"""
Capital Allocator.
Allocates capital across multiple trading strategies like a hedge fund.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from qtrader.core.logger import logger


class CapitalAllocator:
    """
    Allocates capital across multiple strategies based on risk and performance.
    """

    EPSILON = 1e-6
    MIN_STRATEGIES_CORR = 2

    def __init__(
        self,
        max_capital_per_strategy: float = 0.40,
        min_strategies: int = 2,
        correlation_threshold: float = 0.70
    ):
        self.max_capital_per_strategy = max_capital_per_strategy
        self.min_strategies = min_strategies
        self.correlation_threshold = correlation_threshold

    def allocate(
        self,
        strategy_stats: pl.DataFrame,
        strategy_returns: pl.DataFrame | None = None
    ) -> dict[str, float]:
        """
        Calculate capital allocation for each strategy.
        
        Args:
            strategy_stats: DataFrame with [strategy_id, volatility, sharpe, max_drawdown]
            strategy_returns: Optional returns per strategy for correlation
            
        Returns:
            Dictionary mapping strategy_id to capital allocation (0.0 to 1.0)
        """
        try:
            if strategy_stats.is_empty():
                return {}

            # 1. Base Weights: Risk Parity (Inverse Volatility)
            # Avoid division by zero
            vols = strategy_stats["volatility"].to_numpy()
            vols = np.where(vols < self.EPSILON, self.EPSILON, vols)
            inv_vols = 1.0 / vols
            
            # 2. Performance Adjustments
            sharpes = strategy_stats["sharpe"].to_numpy()
            # Floor Sharpe at 0.1 to avoid zeroing out decent strategies
            sharpe_adj = np.maximum(0.1, sharpes)
            
            drawdowns = strategy_stats["max_drawdown"].to_numpy()
            # Penalty increases with drawdown
            dd_adj = 1.0 - np.minimum(0.9, drawdowns)
            
            # Combine factors
            raw_weights = inv_vols * sharpe_adj * dd_adj
            
            # 3. Correlation Penalty
            if strategy_returns is not None and strategy_returns.width >= self.MIN_STRATEGIES_CORR:
                # Exclude 'timestamp' if present
                ret_cols = [c for c in strategy_returns.columns if c != "timestamp"]
                corr_matrix = strategy_returns.select(ret_cols).corr().to_numpy()
                
                # Average absolute correlation per strategy (excluding diagonal)
                n = corr_matrix.shape[0]
                total_corr = np.sum(np.abs(corr_matrix), axis=0) - 1.0
                avg_corr = total_corr / (n - 1) if n > 1 else np.zeros(n)
                
                # Reduce weight for highly correlated strategies
                corr_penalty = 1.0 - (avg_corr ** 2)
                raw_weights = raw_weights * corr_penalty

            # 4. Normalize to 1.0
            total_raw = np.sum(raw_weights)
            if total_raw == 0:
                # Fallback to equal weight
                weights = np.ones(len(strategy_stats)) / len(strategy_stats)
            else:
                weights = raw_weights / total_raw
                
            for _ in range(5):  # Max 5 iterations for convergence
                capped = np.minimum(self.max_capital_per_strategy, weights)
                excess = 1.0 - np.sum(capped)
                if abs(excess) < self.EPSILON:
                    weights = capped
                    break
                
                # Redistribute excess to uncapped strategies
                uncapped_mask = weights < self.max_capital_per_strategy
                if not np.any(uncapped_mask):
                    weights = capped
                    break
                    
                sum_uncapped = np.sum(weights[uncapped_mask])
                weights[uncapped_mask] += excess * (weights[uncapped_mask] / sum_uncapped)
                weights = np.minimum(self.max_capital_per_strategy, weights)

            # Final normalization to ensure sum is 1.0 exactly
            weights = weights / np.sum(weights)
            
            strategy_ids = strategy_stats["strategy_id"].to_list()
            return dict(zip(strategy_ids, weights.tolist(), strict=False))

        except Exception as e:
            logger.error(f"Capital allocation failed: {e}")
            return {}
