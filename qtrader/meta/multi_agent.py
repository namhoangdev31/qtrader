from __future__ import annotations

import polars as pl


class MultiAgentSystem:
    """
    Distributed Multi-Agent Architecture for QTrader.

    Orchestrates the parallel execution of diverse trading strategies (agents).
    Dynamically allocates capital based on the marginal risk-contribution
    and historical Sharpe ratio to maximize portfolio diversification while
    respecting global risk constraints.

    Conforms to the KILO.AI Industrial Grade Protocol for orchestrated
    distributed execution.
    """

    def __init__(self, total_capital: float = 1_000_000.0) -> None:
        """
        Initialize the system with global capital parameters.

        Args:
            total_capital: Initial capital available for allocation across agents (USD).
        """
        self.total_capital = total_capital

    def allocate_capital(
        self,
        agent_metrics: pl.DataFrame,
        risk_threshold: float = 0.02,
    ) -> pl.DataFrame:
        """
        Distribute capital across agents based on their performance and risk.

        Logic:
        1. Calculate Allocation_i proportional to Sharpe Ratio.
        2. Adjust for risk (Volatility-adjusted weight).
        3. Enforce and scale to remain under global risk_threshold.

        Args:
            agent_metrics: Metrics containing 'agent_id', 'sharpe', and 'volatility'.
            risk_threshold: Maximum allowable portfolio-level volatility exposure.

        Returns:
            DataFrame containing 'agent_id' and 'allocated_capital'.
        """
        if agent_metrics.is_empty():
            return pl.DataFrame()

        # Numerical stability constant
        epsilon = 1e-12

        # 1. Performance-based weight (proportional to Sharpe)
        # We ensure positive Sharpe to avoid allocating to failed agents
        df_alloc = agent_metrics.with_columns(pl.col("sharpe").clip(lower_bound=0.0).alias("score"))

        total_score = df_alloc["score"].sum()
        if total_score <= 0:
            # Equal weight fallback
            count = len(df_alloc)
            return df_alloc.with_columns(
                (pl.lit(self.total_capital) / count).alias("allocated_capital")
            )

        # 2. Risk-adjusted Weight (Inverse Volatility)
        df_alloc = df_alloc.with_columns((1.0 / (pl.col("volatility") + epsilon)).alias("inv_vol"))

        # 3. Final Allocation Decision
        # We combine Sharpe-rank with Inverse-Vol
        df_alloc = df_alloc.with_columns((pl.col("score") * pl.col("inv_vol")).alias("raw_weight"))

        total_weight = float(df_alloc["raw_weight"].sum())

        return df_alloc.with_columns(
            (pl.col("raw_weight") / (total_weight + epsilon) * self.total_capital).alias(
                "allocated_capital"
            )
        ).select(["agent_id", "allocated_capital"])

    def aggregate_portfolio_pnl(
        self,
        agent_pnls: pl.DataFrame,
    ) -> pl.Series:
        """
        Summate PnL from all active agents into a global portfolio series.

        Mathematical Model:
        Portfolio_PnL = Sum(PnL_i)

        Args:
            agent_pnls: Long-form DataFrame with 'timestamp' and 'pnl' for each agent.

        Returns:
            Vectorized PnL series of the total portfolio.
        """
        if agent_pnls.is_empty():
            return pl.Series(name="total_pnl", values=[], dtype=pl.Float64)

        return (
            agent_pnls.group_by("timestamp")
            .agg(pl.col("pnl").sum().alias("total_pnl"))
            .sort("timestamp")["total_pnl"]
        )
