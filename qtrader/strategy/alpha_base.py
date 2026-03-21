from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

import polars as pl

_LOG = logging.getLogger("qtrader.strategy.alpha")


class Alpha(ABC):
    """
    Abstract base layer for alpha factors (feature engineering).

    Alpha factors are pure feature generators that output continuous, normalized
    feature values (z-scores). They must NOT contain any signal generation or
    discrete decision logic.

    Contract:
        - Input:  pl.DataFrame with OHLCV columns (open, high, low, close, volume)
        - Output: pl.Series of dtype Float64, same length as input
        - The output must be continuous and normalized (e.g., z-scored).
    """

    # Define the minimum required OHLCV columns
    REQUIRED_COLUMNS: ClassVar[list[str]] = ["open", "high", "low", "close", "volume"]

    @abstractmethod
    def _compute(self, df: pl.DataFrame) -> pl.Series:
        """
        Compute the alpha factor from the input data.

        This method must be implemented by subclasses to return a feature series.

        Args:
            df: Input DataFrame with at least the REQUIRED_COLUMNS.

        Returns:
            A pl.Series of dtype Float64 representing the alpha factor.
            The length must match the input DataFrame's height.
        """
        pass

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """
        Public method to compute the alpha factor with validation and fallback.

        This method:
            1. Validates the presence of REQUIRED_COLUMNS.
            2. On validation failure, logs a warning and returns a neutral fallback
               series (all zeros) of the same length as input, dtype Float64.
            3. On success, calls the subclass's _compute method.
            4. Validates the output of _compute: must be a pl.Series, same length
               as input, and dtype Float64.
            5. If _compute output fails validation, logs a warning and returns the
               neutral fallback.

        Args:
            df: Input DataFrame with OHLCV data.

        Returns:
            A pl.Series of dtype Float64, same length as input.
        """
        # Validation: check required columns
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            _LOG.warning(
                "Alpha %s missing required columns %s. Returning neutral fallback.",
                self.__class__.__name__,
                missing_cols,
            )
            return pl.Series([0.0] * len(df), dtype=pl.Float64).alias(
                self.__class__.__name__
            )

        # Delegate to subclass
        try:
            result = self._compute(df)
        except Exception as e:
            _LOG.warning(
                "Alpha %s raised an exception during _compute: %s. Returning neutral fallback.",
                self.__class__.__name__,
                str(e),
            )
            return pl.Series([0.0] * len(df), dtype=pl.Float64).alias(
                self.__class__.__name__
            )

        # Validate output
        if not isinstance(result, pl.Series):
            _LOG.warning(
                "Alpha %s._compute did not return a pl.Series (got %s). Returning neutral fallback.",
                self.__class__.__name__,
                type(result).__name__,
            )
            return pl.Series([0.0] * len(df), dtype=pl.Float64).alias(
                self.__class__.__name__
            )

        if result.len() != len(df):
            _LOG.warning(
                "Alpha %s output length (%d) does not match input length (%d). Returning neutral fallback.",
                self.__class__.__name__,
                result.len(),
                len(df),
            )
            return pl.Series([0.0] * len(df), dtype=pl.Float64).alias(
                self.__class__.__name__
            )

        if result.dtype != pl.Float64:
            _LOG.warning(
                "Alpha %s output dtype is %s, expected Float64. Returning neutral fallback.",
                self.__class__.__name__,
                result.dtype,
            )
            return pl.Series([0.0] * len(df), dtype=pl.Float64).alias(
                self.__class__.__name__
            )

        # Optionally, we could enforce that the series is normalized (z-scored) here,
        # but the contract states that the alpha should output normalized values.
        # We leave normalization to the subclass, but we could issue a warning if
        # the values are not roughly normalized (e.g., mean far from 0, std far from 1).
        # For now, we trust the subclass to produce normalized output.

        return result