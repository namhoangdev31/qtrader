from __future__ import annotations

import polars as pl

from qtrader.risk.base import RiskModule


class DrawdownControl(RiskModule):
    """
    Drawdown control risk module.

    Computes a position scaling factor based on the current drawdown from the equity peak.
    Implements a soft and hard limit with linear decay between them.

    The scaling factor is:
        - 1.0 when drawdown <= soft_limit
        - 0.0 when drawdown >= hard_limit
        - linear between 1.0 and 0.0 for soft_limit < drawdown < hard_limit

    This helps to reduce exposure during drawdown periods to prevent further losses.

    Args:
        max_dd_threshold: Maximum allowed drawdown (e.g., 0.2 for 20%).
        soft_limit_pct: Fraction of max_dd_threshold where scaling starts to decay (default 0.5).
        hard_limit_pct: Fraction of max_dd_threshold where scaling reaches 0.0 (default 0.8).
        equity_column: Column name in data containing equity curve (default 'equity').
        returns_column: Column name in data containing period returns (default 'returns').
                       Used to compute equity if equity_column is not present.
    """

    def __init__(
        self,
        max_dd_threshold: float = 0.2,
        soft_limit_pct: float = 0.5,
        hard_limit_pct: float = 0.8,
        equity_column: str = 'equity',
        returns_column: str = 'returns',
    ) -> None:
        if max_dd_threshold <= 0:
            raise ValueError("max_dd_threshold must be positive")
        if not 0 < soft_limit_pct < hard_limit_pct < 1:
            raise ValueError("Must have 0 < soft_limit_pct < hard_limit_pct < 1")
        self.max_dd_threshold = max_dd_threshold
        self.soft_limit = max_dd_threshold * soft_limit_pct
        self.hard_limit = max_dd_threshold * hard_limit_pct
        self.equity_column = equity_column
        self.returns_column = returns_column

    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        """
        Compute the drawdown-based position scaling factor.

        Args:
            data: Input DataFrame containing either an equity column or returns column.
            **kwargs: Additional parameters (ignored).

        Returns:
            A pl.Series of dtype Float64 representing the drawdown scaling factor.
            Length matches the input DataFrame's height.
        """
        # Get equity curve
        if self.equity_column in data.columns:
            equity = data[self.equity_column]
        elif self.returns_column in data.columns:
            # Compute equity from returns: (1 + r).cum_prod()
            equity = (1.0 + data[self.returns_column]).cum_prod()
        else:
            raise ValueError(
                f"Data must contain either '{self.equity_column}' or '{self.returns_column}' column"
            )

        # Compute running maximum of equity
        roll_max = equity.cum_max()
        # Compute drawdown: (roll_max - equity) / roll_max
        # When roll_max is 0, set drawdown to 0 to avoid division by zero
        drawdown_expr = pl.when(roll_max == 0).then(0.0).otherwise((roll_max - equity) / roll_max)

        # Compute scaling factor based on drawdown thresholds
        scaling_factor_expr = pl.when(
            drawdown_expr <= self.soft_limit
        ).then(
            1.0
        ).otherwise(
            pl.when(
                drawdown_expr >= self.hard_limit
            ).then(
                0.0
            ).otherwise(
                (self.hard_limit - drawdown_expr) / (self.hard_limit - self.soft_limit)
            )
        )

        # Evaluate the expression on the DataFrame to get a Series
        scaling_factor_series = data.select(scaling_factor_expr.alias("drawdown_scaling")).to_series()

        return scaling_factor_series