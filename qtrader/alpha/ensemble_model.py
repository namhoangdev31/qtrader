from __future__ import annotations

import polars as pl


class AlphaEnsemble:
    """
    Combines multiple alpha signals into a single performance-weighted signal.

    Mathematical Model:
    - Weight: w_i = (IC_i / sigma_i) / sum(abs(IC_j / sigma_j))
    - Ensemble: S = sum(w_i * S_i)
    """

    @staticmethod
    def calculate_weights(metrics: dict[str, dict[str, float]]) -> dict[str, float]:
        """
        Compute normalized weights based on IC and volatility.

        Args:
            metrics: Dict mapping signal_id to {'ic': float, 'std': float}.

        Returns:
            Dict mapping signal_id to normalized weight.
        """
        if not metrics:
            return {}

        raw_weights: dict[str, float] = {}
        total_abs_weight: float = 0.0

        for signal_id, stats in metrics.items():
            ic = stats.get("ic", 0.0)
            vol = stats.get("std", 1.0)

            # Avoid division by zero
            safe_vol = max(vol, 1e-6)
            weight = ic / safe_vol

            raw_weights[signal_id] = weight
            total_abs_weight += abs(weight)

        if total_abs_weight == 0:
            # Equal weight fallback if all performance is zero
            n = len(metrics)
            return {s: 1.0 / n for s in metrics}

        return {s: w / total_abs_weight for s, w in raw_weights.items()}

    @staticmethod
    def combine_signals(df: pl.DataFrame, weights: dict[str, float]) -> pl.Series:
        """
        Aggregate multiple signal columns into a single ensemble Series.

        Args:
            df: DataFrame containing signal columns.
            weights: Dict mapping column name to weight.

        Returns:
            Weighted ensemble signal Series.
        """
        if df.is_empty() or not weights:
            return pl.Series("ensemble_signal", [])

        ensemble_expr = pl.lit(0.0)
        for col_name, weight in weights.items():
            if col_name in df.columns:
                ensemble_expr += pl.col(col_name) * weight

        return df.select(ensemble_expr.alias("ensemble_signal"))["ensemble_signal"]
