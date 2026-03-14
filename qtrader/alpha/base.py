from __future__ import annotations

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
