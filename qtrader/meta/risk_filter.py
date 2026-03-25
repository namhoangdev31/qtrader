from __future__ import annotations

import polars as pl


class RiskFilter:
    """
    Automated Quantitative Risk Controller.

    Serves as the final safety gate before model deployment. Evaluates
    candidate strategies against strict risk benchmarks including Maximum
    Drawdown (MDD) and Value at Risk (VaR). Strategies failing these checks
    are permanently blacklisted for the current research cycle.

    Conforms to the KILO.AI Industrial Grade Protocol for zero-manual-intervention
    risk governance.
    """

    @staticmethod
    def filter_risky_candidates(
        metrics_df: pl.DataFrame,
        max_drawdown_threshold: float = 0.15,
        var_threshold: float = 0.03,
    ) -> pl.DataFrame:
        """
        Prune strategies that violate risk thresholds.

        Mathematical Model:
        Valid = (Max_Drawdown <= Threshold_MDD) AND (VaR <= Threshold_VaR)

        Args:
            metrics_df: DataFrame containing 'config_id', 'max_drawdown', and 'var'.
            max_drawdown_threshold: Maximum allowable peak-to-trough decline (0.15 = 15%).
            var_threshold: Maximum allowable daily Value at Risk (0.03 = 3%).

        Returns:
            Filtered DataFrame containing only 'Safe' strategies.
        """
        if metrics_df.is_empty():
            return metrics_df

        # 1. Verification of MDD constraints
        # 2. Verification of Volatility/VaR constraints
        # 3. Intersection of safety conditions

        return metrics_df.filter(
            (pl.col("max_drawdown") <= max_drawdown_threshold) & (pl.col("var") <= var_threshold)
        )

    @staticmethod
    def calculate_capital_haircut(
        metrics_df: pl.DataFrame,
        base_haircut: float = 0.1,
    ) -> pl.DataFrame:
        """
        Compute dynamic capital adjustments based on tail risk.

        Haircut = Base + Max_Drawdown

        Args:
            metrics_df: Agent performance metrics.
            base_haircut: Minimal capital buffer required.

        Returns:
            Enriched DataFrame with 'capital_multiplier'.
        """
        if metrics_df.is_empty():
            return metrics_df

        return metrics_df.with_columns(
            (1.0 - (base_haircut + pl.col("max_drawdown"))).alias("capital_multiplier")
        ).with_columns(pl.col("capital_multiplier").clip(lower_bound=0.0, upper_bound=1.0))
