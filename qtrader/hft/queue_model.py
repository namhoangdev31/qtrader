from __future__ import annotations

import polars as pl


class QueueModel:
    """
    Orderbook Queue Dynamics Model.

    Predicts the likelihood of a limit order being executed at a specific price level
    given the queue depth and real-time execution rates. This model is critical
    for Smart Order Routing (SOR) and passively capturing the spread.

    Conforms to the KILO.AI Industrial Grade Protocol for sub-millisecond
    probabilistic modeling using vectorized Polars logic.
    """

    @staticmethod
    def estimate_fill_probability(
        df: pl.DataFrame,
        queue_depth_col: str = "bid_vol_0",
        exec_rate_col: str = "exec_rate_rolling",
        horizon_seconds: float = 1.0,
    ) -> pl.Series:
        """
        Estimate the fill probability across a batch of orderbook snapshots.

        Mathematical Model:
        P(fill) = min(1.0, (ExecutionRate * Horizon) / QueueDepth)

        Args:
            df: DataFrame containing queue volume and rolling execution velocity.
            queue_depth_col: Column representing total volume at the target price level.
            exec_rate_col: Rolling average of executed volume per second at this level.
            horizon_seconds: Time window for the execution event.

        Returns:
            Polars Series of fill probabilities [0, 1].
        """
        if df.is_empty():
            return pl.Series(name="fill_prob", values=[], dtype=pl.Float64)

        # Numerical stability constant
        epsilon = 1e-12

        # 1. Projected Total Execution (E[V_exec])
        projected_execution = pl.col(exec_rate_col) * horizon_seconds

        # 2. Fill Probability Calculation
        raw_prob = projected_execution / (pl.col(queue_depth_col) + epsilon)

        # 3. Constraint Normalization
        # Clamps values to the valid [0, 1] probability interval
        return df.select(
            pl.when(raw_prob > 1.0)
            .then(pl.lit(1.0))
            .otherwise(pl.when(raw_prob < 0.0).then(pl.lit(0.0)).otherwise(raw_prob))
            .alias("fill_prob")
        )["fill_prob"]

    @staticmethod
    def estimate_wait_time(
        queue_depth: float,
        avg_exec_rate: float,
    ) -> float:
        """
        Estimate time until full execution (T_fill).

        T_fill = QueueDepth / (AvgExecutionRate + epsilon)

        Args:
            queue_depth: Current depth of the queue.
            avg_exec_rate: Units of volume executed per second.

        Returns:
            Wait time in seconds.
        """
        epsilon = 1e-12
        return queue_depth / (avg_exec_rate + epsilon)
