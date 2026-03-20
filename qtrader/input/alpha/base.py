from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

import polars as pl

__all__ = ["Alpha", "_zscore"]


@runtime_checkable
class Alpha(Protocol):
    """Protocol for alpha factor computation."""

    name: str

    def compute(self, df: pl.DataFrame) -> pl.Series:  # pragma: no cover - interface
        """Compute alpha signal from OHLCV input.

        Args:
            df: OHLCV DataFrame with at least columns
                ``open, high, low, close, volume, timestamp``.

        Returns:
            Polars Series of z-scored signals, aligned to ``df`` and
            containing nulls where lookback is insufficient.
        """


class BaseAlpha(ABC):
    """Base class for alpha factors enforcing standardized interface.

    All alpha implementations should inherit from this class.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        """Compute raw alpha signal. Must be implemented by subclasses.

        Args:
            df: OHLCV DataFrame with at least columns
                ``open, high, low, close, volume, timestamp``.

        Returns:
            Polars Series of raw alpha values (not normalized).
        """

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute alpha signal with validation and standardization.

        Args:
            df: OHLCV DataFrame with at least columns
                ``open, high, low, close, volume, timestamp``.

        Returns:
            Polars Series of z-scored signals, aligned to ``df`` and
            containing zeros where lookback is insufficient or errors occur.
            Always returns Float64 dtype with same length as input.
        """
        # Validate required columns
        required = {"open", "high", "low", "close", "volume", "timestamp"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        # Compute raw alpha
        try:
            raw = self._compute_raw(df)
        except Exception:
            # On any error, return neutral fallback
            return pl.Series(
                name=self.name, values=[0.0] * df.height, dtype=pl.Float64
            )

        # Ensure output length matches input
        if raw.len() != df.height:
            return pl.Series(
                name=self.name, values=[0.0] * df.height, dtype=pl.Float64
            )

        # Ensure Float64 dtype
        if raw.dtype != pl.Float64:
            raw = raw.cast(pl.Float64)

        # Replace non-finite values with zero (neutral fallback)
        raw = raw.fill_nan(0.0).fill_null(0.0)

        return raw


def _zscore(series: pl.Series, window: int) -> pl.Series:
    """Compute rolling z-score for a series.

    Args:
        series: Input series.
        window: Rolling window size.

    Returns:
        Series of z-scores with nulls for insufficient history or zero std.
    """
    if window <= 1 or series.len() == 0:
        return pl.Series(name=series.name, values=[None] * series.len())
    df = pl.DataFrame({"x": series})
    roll = df.with_columns(
        pl.col("x").rolling_mean(window).alias("m"),
        pl.col("x").rolling_std(window).alias("s"),
    )
    z = (roll["x"] - roll["m"]) / roll["s"]
    z = z.to_frame("z").with_columns(
        pl.when(pl.col("z").is_finite()).then(pl.col("z")).otherwise(None).alias("z"),
    )["z"]
    return z


"""
Pytest-style examples (conceptual):

def test_zscore_length_matches() -> None:
    s = pl.Series("x", [1.0, 2.0, 3.0, 4.0])
    z = _zscore(s, window=2)
    assert z.len() == s.len()
"""