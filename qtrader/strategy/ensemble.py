from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    from qtrader.core.event import SignalEvent
    from qtrader.strategy.base import BaseStrategy


class EnsembleStrategy(ABC):
    """
    Base class for ensemble strategies that combine multiple strategies.
    """

    def __init__(self, strategies: list[BaseStrategy]) -> None:
        """
        Initialize the ensemble strategy.

        Args:
            strategies: List of strategies to combine.
        """
        self.strategies = strategies

    @abstractmethod
    def compute_signals(self, features: dict[str, pl.Series]) -> SignalEvent:
        """
        Compute signals by combining outputs from all sub-strategies.

        Args:
            features: Dictionary mapping alpha names to their feature series.

        Returns:
            SignalEvent containing combined signal and metadata.
        """
        pass

    @abstractmethod
    def update_weights(self, performance_metrics: dict[str, float]) -> None:
        """
        Update strategy weights based on performance.

        Args:
            performance_metrics: Dictionary mapping strategy identifiers to performance scores.
        """
        pass