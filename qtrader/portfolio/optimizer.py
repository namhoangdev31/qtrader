"""Base classes for portfolio optimizers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import polars as pl
import numpy as np


class AllocatorBase(ABC):
    """Abstract base class for portfolio allocators."""

    @abstractmethod
    def allocate(
        self,
        returns: Optional[pl.DataFrame] = None,
        covariance: Optional[np.ndarray] = None,
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
