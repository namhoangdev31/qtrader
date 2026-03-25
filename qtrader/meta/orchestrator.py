from __future__ import annotations

import polars as pl


class SystemOrchestrator:
    """
    Global Meta-System Orchestrator.

    Integrates outputs from various Alpha models and HFT signals into a
    unified execution decision. Dynamically adjusts model weights (w_i)
    based on their historical risk-adjusted efficiency (Ensemble Learning).

    Conforms to the KILO.AI Industrial Grade Protocol for orchestrated
    high-frequency decision making.
    """

    @staticmethod
    def compute_ensemble_signal(
        signals_df: pl.DataFrame,
        model_weights: dict[str, float],
    ) -> pl.Series:
        """
        Produce a weighted consensus signal from multiple models.

        Mathematical Model:
        Consensus = Sum(w_i * Signal_i) / Sum(w_i)

        Args:
            signals_df: DataFrame where each column is a model signal.
            model_weights: Dictionary mapping signal column names to their
                respective performance weights.

        Returns:
            Polars Series of the resulting ensemble signal.
        """
        if signals_df.is_empty() or not model_weights:
            return pl.Series(name="ensemble", values=[], dtype=pl.Float64)

        # Numerical stability epsilon
        epsilon = 1e-12

        # 1. Summation of weighted contributions
        weighted_sum = pl.lit(0.0)
        total_weight = 0.0

        for model_id, weight in model_weights.items():
            if model_id in signals_df.columns:
                weighted_sum = weighted_sum + (pl.col(model_id) * weight)
                total_weight += weight

        # 2. Final Normalization
        final_signal = weighted_sum / (total_weight + epsilon)

        return signals_df.select(final_signal.alias("ensemble"))["ensemble"]

    @staticmethod
    def adapt_weights(
        performance_metrics: pl.DataFrame,
        target_metric: str = "sharpe",
    ) -> dict[str, float]:
        """
        Dynamically calculate new model weights based on performance.

        Logic:
        w_i = Performance_i / Sum(Performance_j)
        (Using Softmax or absolute clipping for stabilization).

        Args:
            performance_metrics: DataFrame containing 'model_id' and various metrics.
            target_metric: Metric to use for weight attribution (e.g. 'ic' or 'sharpe').

        Returns:
            Dictionary of model_id -> weight.
        """
        if performance_metrics.is_empty():
            return {}

        # Ensure metrics are positive for simple proportional weighting
        # We use a softmax-like approach for differentiation
        df_weights = performance_metrics.with_columns(
            pl.col(target_metric).clip(lower_bound=0.0).alias("positive_perf")
        )

        total_perf = df_weights["positive_perf"].sum()
        if total_perf <= 0:
            # Fallback to equal weight
            count = len(df_weights)
            equal_w = 1.0 / count if count > 0 else 0.0
            return {row["model_id"]: equal_w for row in df_weights.to_dicts()}

        df_weights = df_weights.with_columns((pl.col("positive_perf") / total_perf).alias("weight"))

        return {
            str(row["model_id"]): float(row["weight"])
            for row in df_weights.select(["model_id", "weight"]).to_dicts()
        }
