from __future__ import annotations

from typing import Any

import polars as pl


class AlphaMetaSelector:
    """
    Automated Alpha Selection Engine.

    Ranking and selection of best performing alpha factors based on
    a multi-objective score (Sharpe_Ratio * Pearson_IC). This selector
    enables the Global Orchestrator to prune the alpha pool and concentrate
    execution capital on high-quality signals.
    """

    def __init__(self, top_k: int = 10) -> None:
        """
        Initialize the selector.

        Args:
            top_k: Number of best alphas to retain from the pool.
        """
        self.top_k = top_k

    def select_best_alphas(
        self, alpha_pool: list[str], performance_metrics: pl.DataFrame
    ) -> list[str]:
        """
        Rank and select the top K alphas.

        Mathematical Model:
        Score_i = Sharpe_i * IC_i

        Logic:
        1. Filters performance metrics for alphas in the pool.
        2. Computes the selection score.
        3. Ranks alphas in descending order.
        4. Selects the Top-K.

        Args:
            alpha_pool: List of alpha identifiers (names).
            performance_metrics: DataFrame containing:
                - 'name': str, Alpha identifier.
                - 'sharpe': float, Risk-adjusted return.
                - 'ic': float, Information coefficient (predictive power).

        Returns:
            List of selected alpha names, sorted by score.
        """
        if performance_metrics.is_empty():
            return alpha_pool[: self.top_k]

        # Standardize schema check
        required_cols = {"name", "sharpe", "ic"}
        actual_cols = set(performance_metrics.columns)
        if not required_cols.issubset(actual_cols):
            # Fallback to simple pool slice if schema is incorrect
            return alpha_pool[: self.top_k]

        # 1. Compute Score, Rank and Select Top-K
        selected_df = (
            performance_metrics.filter(pl.col("name").is_in(alpha_pool))
            .with_columns((pl.col("sharpe") * pl.col("ic")).alias("selection_score"))
            .sort("selection_score", descending=True)
            .head(self.top_k)
        )

        return selected_df["name"].to_list()

    def get_pool_diagnostics(self, performance_metrics: pl.DataFrame) -> dict[str, Any]:
        """
        Compute summary statistics for the current selection pool.

        Args:
            performance_metrics: DataFrame of alpha metrics.

        Returns:
            Dict containing mean Sharpe, mean IC, and pool diversity stats.
        """
        if performance_metrics.is_empty():
            return {}

        agg = performance_metrics.select(
            [
                pl.col("sharpe").mean().alias("avg_sharpe"),
                pl.col("sharpe").median().alias("median_sharpe"),
                pl.col("ic").mean().alias("avg_ic"),
                pl.col("ic").std().alias("ic_std"),
            ]
        ).to_dicts()

        return agg[0] if agg else {}
