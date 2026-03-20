from __future__ import annotations

import polars as pl

from qtrader.risk.base import RiskModule


class VolatilityTargeting(RiskModule):
    """
    Volatility targeting risk module.

    Computes a volatility scaling factor to target a constant portfolio volatility.
    The scaling factor is calculated as: target_vol / current_vol
    where current_vol is the rolling standard deviation of returns (annualized).

    This module outputs a continuous scaling factor series that can be used to
    adjust position sizes.
    """

    def __init__(
        self,
        lookback: int = 30,
        target_vol: float = 0.01,
        annualize: bool = True,
        trading_periods: int = 252,
        epsilon: float = 1e-8,
    ) -> None:
        """
        Initialize the VolatilityTargeting module.

        Args:
            lookback: Lookback period for rolling volatility calculation.
            target_vol: Target annualized volatility (e.g., 0.01 for 1%).
            annualize: Whether to annualize the volatility.
            trading_periods: Number of trading periods in a year for annualization.
            epsilon: Small value to avoid division by zero.
        """
        self.lookback = lookback
        self.target_vol = target_vol
        self.annualize = annualize
        self.trading_periods = trading_periods
        self.epsilon = epsilon

    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        """
        Compute the volatility scaling factor.

        Args:
            data: Input DataFrame with at least a 'close' column.
            **kwargs: Additional parameters (ignored in this module).

        Returns:
            A pl.Series of dtype Float64 representing the volatility scaling factor.
            Length matches the input DataFrame's height.
        """
        # Calculate simple returns: (close_t / close_{t-1}) - 1
        returns_expr = pl.col("close").pct_change()

        # Compute rolling standard deviation of returns (volatility)
        volatility_expr = returns_expr.rolling_std(window_size=self.lookback)

        # Annualize volatility if requested
        if self.annualize:
            volatility_expr = volatility_expr * (self.trading_periods ** 0.5)

        # Avoid division by zero and handle NaN/inf
        # When volatility is 0 or NaN, set scaling factor to 0 (no position)
        # Otherwise, scaling factor = target_vol / (volatility + epsilon)
        scaling_factor_expr = pl.when(
            (volatility_expr.is_not_null()) & (volatility_expr != 0) & (volatility_expr != float('inf')) & (volatility_expr != float('-inf'))
        ).then(
            self.target_vol / (volatility_expr + self.epsilon)
        ).otherwise(0.0)

        # Compute the scaling factor series
        scaling_factor = data.with_columns(
            scaling_factor_expr.alias("volatility_scaling")
        )["volatility_scaling"]

        return scaling_factor