from __future__ import annotations

import polars as pl

from qtrader.strategy.alpha_base import Alpha


class MomentumAlpha(Alpha):
    """
    Momentum alpha factor: z-scored returns over a lookback window.

    Computes the z-score of the simple returns (close_t / close_{t-1} - 1)
    over a rolling window. The output is normalized (mean 0, std 1) within
    the window, except for periods where the standard deviation is zero
    (output 0) or insufficient data (output 0).

    This is a pure feature generator: it returns continuous values and
    contains no signal generation logic.
    """

    def __init__(self, lookback: int = 30) -> None:
        """
        Initialize the MomentumAlpha.

        Args:
            lookback: The lookback window for computing rolling mean and std.
                      Default is 30 periods.
        """
        super().__init__()
        self.lookback = lookback

    def _compute(self, df: pl.DataFrame) -> pl.Series:
        """
        Compute the momentum alpha factor.

        Args:
            df: Input DataFrame with at least the columns ["open", "high", "low", "close", "volume"].

        Returns:
            A pl.Series of dtype Float64 representing the z-scored returns.
            The length matches the input DataFrame's height.
        """
        # Calculate simple returns: (close_t / close_{t-1}) - 1
        returns_expr = pl.col("close").pct_change()

        # Compute rolling mean and standard deviation of returns
        rolling_mean_expr = returns_expr.rolling_mean(window_size=self.lookback)
        rolling_std_expr = returns_expr.rolling_std(window_size=self.lookback)

        # Avoid division by zero: when rolling_std is 0, set z_score to 0
        # Otherwise, compute z-score = (returns - rolling_mean) / rolling_std
        z_score_expr = pl.when(rolling_std_expr == 0).then(0.0).otherwise(
            (returns_expr - rolling_mean_expr) / rolling_std_expr
        )

        # Fill any remaining nulls (from insufficient data for rolling operations) with 0.0
        z_score_expr = z_score_expr.fill_null(0.0)

        # Evaluate the expression on the DataFrame to get a Series
        result_series = df.select(z_score_expr.alias("momentum_alpha")).to_series()

        return result_series