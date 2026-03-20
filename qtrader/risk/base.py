from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class RiskModule(ABC):
    """
    Abstract base class for risk management modules.

    Risk modules take in market data and/or signals and output risk-adjusted
    values such as position sizes, volatility scalars, or risk limits.
    """

    @abstractmethod
    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        """
        Compute the risk metric.

        Args:
            data: Input DataFrame containing necessary market data.
            **kwargs: Additional parameters (e.g., signals for position sizing).

        Returns:
            A pl.Series of dtype Float64 representing the computed risk metric.
        """
        pass