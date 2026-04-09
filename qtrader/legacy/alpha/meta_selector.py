from __future__ import annotations
from typing import Any
import polars as pl


class AlphaMetaSelector:
    def __init__(self, top_k: int = 10) -> None:
        self.top_k = top_k

    def select_best_alphas(
        self, alpha_pool: list[str], performance_metrics: pl.DataFrame
    ) -> list[str]:
        if performance_metrics.is_empty():
            return alpha_pool[: self.top_k]
        required_cols = {"name", "sharpe", "ic"}
        actual_cols = set(performance_metrics.columns)
        if not required_cols.issubset(actual_cols):
            return alpha_pool[: self.top_k]
        selected_df = (
            performance_metrics.filter(pl.col("name").is_in(alpha_pool))
            .with_columns((pl.col("sharpe") * pl.col("ic")).alias("selection_score"))
            .sort("selection_score", descending=True)
            .head(self.top_k)
        )
        return selected_df["name"].to_list()

    def get_pool_diagnostics(self, performance_metrics: pl.DataFrame) -> dict[str, Any]:
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
