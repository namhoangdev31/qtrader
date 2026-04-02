"""Base classes for portfolio optimizers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    import polars as pl


class AllocatorBase(ABC):
    """Abstract base class for portfolio allocators."""

    @abstractmethod
    def allocate(
        self,
        returns: pl.DataFrame | None = None,
        covariance: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Allocate portfolio weights.

        Args:
            returns: Historical returns DataFrame (time x assets).
            covariance: Precomputed covariance matrix (assets x assets).

        Returns:
            Array of portfolio weights (assets,).
        """
        pass
