from __future__ import annotations

import polars as pl


class MetaAlphaSelector:
    """
    Selects the best alpha signal for a given market regime.

    Mathematical Model:
    - P(alpha | regime) ∝ MeanPerformance(alpha, regime)
    """

    def __init__(self) -> None:
        # Map: regime_id -> { alpha_id: mean_performance }
        self._regime_performance: dict[int, dict[str, float]] = {}

    def fit(
        self, df: pl.DataFrame, signal_cols: list[str], regime_col: str, metric_col: str
    ) -> None:
        """
        Build the regime-to-performance mapping from history.

        Args:
            df: DataFrame with signals, regimes, and performance metrics.
            signal_cols: List of signal IDs/column names.
            regime_col: Column identifying market regimes.
            metric_col: Column containing performance metric (e.g. 'ic').
        """
        if df.is_empty():
            return

        if signal_cols and all(col in df.columns for col in signal_cols):
            long_df = df.unpivot(
                index=[regime_col],
                on=signal_cols,
                variable_name="signal_id",
                value_name="performance",
            )
        else:
            long_df = df.rename({metric_col: "performance"})

        summary = (
            long_df.group_by([regime_col, "signal_id"])
            .agg(pl.col("performance").mean())
            .sort([regime_col, "performance"], descending=[False, True])
        )

        for regime_key, group in summary.group_by(regime_col):
            regime_val = regime_key[0] if isinstance(regime_key, tuple) else regime_key
            rid = int(regime_val)
            self._regime_performance[rid] = {
                str(row["signal_id"]): float(row["performance"]) for row in group.to_dicts()
            }

    def recommend_alpha(self, regime_id: int) -> str | None:
        """
        Recommend the top-performing alpha for the current regime.

        Args:
            regime_id: The detected market regime.

        Returns:
            Best signal ID or None if regime is unknown.
        """
        performance_map = self._regime_performance.get(regime_id)
        if not performance_map:
            return None

        # Sort by value and return the top key
        best_alpha: str = max(performance_map, key=performance_map.get)  # type: ignore[arg-type]
        return best_alpha
