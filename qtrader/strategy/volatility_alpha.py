from __future__ import annotations

import polars as pl

from qtrader.strategy.alpha_base import Alpha


class VolatilityAlpha(Alpha):
    """
    Volatility alpha factor: z-scored rolling volatility of returns.

    Computes the rolling standard deviation of returns (close price) over a lookback window,
    then normalizes the volatility series using a z-score (rolling mean and std of volatility).
    The output is a continuous, normalized feature series.

    This is a pure feature generator: it returns continuous values and
    contains no signal generation logic.
    """

    def __init__(self, lookback: int = 30) -> None:
        """
        Initialize the VolatilityAlpha.

        Args:
            lookback: The lookback window for computing rolling volatility and its normalization.
                      Default is 30 periods.
        """
        super().__init__()
        self.lookback = lookback

    def _compute(self, df: pl.DataFrame) -> pl.Series:
        """
        Compute the volatility alpha factor.

        Args:
            df: Input DataFrame with at least the columns ["open", "high", "low", "close", "volume"].

        Returns:
            A pl.Series of dtype Float64 representing the z-scored rolling volatility.
            The length matches the input DataFrame's height.
        """
        # Calculate simple returns: (close_t / close_{t-1}) - 1
        returns_expr = pl.col("close").pct_change()

        # Calculate rolling standard deviation of returns (volatility)
        volatility_expr = returns_expr.rolling_std(window_size=self.lookback)

        # Calculate rolling mean and standard deviation of volatility for z-score normalization
        vol_mean_expr = volatility_expr.rolling_mean(window_size=self.lookback)
        vol_std_expr = volatility_expr.rolling_std(window_size=self.lookback)

        # Avoid division by zero: when vol_std is 0, set normalized volatility to 0
        # Otherwise, compute z-score = (volatility - vol_mean) / vol_std
        normalized_vol_expr = pl.when(vol_std_expr == 0).then(0.0).otherwise(
            (volatility_expr - vol_mean_expr) / vol_std_expr
        )

        # Fill any remaining nulls (from insufficient data for rolling operations) with 0.0
        normalized_vol_expr = normalized_vol_expr.fill_null(0.0)

        # Evaluate the expression on the DataFrame to get a Series
        result_series = df.select(normalized_vol_expr.alias("volatility_alpha")).to_series()

        return result_series