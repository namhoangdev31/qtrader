"""Base protocols for features and factor pipelines.

All feature implementations must satisfy the Feature Protocol.
compute() must be a pure Polars expression chain — no Python loops, no numpy.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import polars as pl

__all__ = ["Feature", "FeaturePipeline"]


@runtime_checkable
class Feature(Protocol):
    """Protocol for a single computed feature or technical indicator.

    All implementors must:
    - Be stateless (no mutable state between compute() calls)
    - Use Polars expressions only (no row-by-row Python loops)
    - Return NaN for the first ``min_periods - 1`` rows
    """

    name: str
    """Unique identifier; used as the output column name in FeatureStore."""

    version: str
    """Semantic version string, e.g. "1.0". Defaults to "1.0"."""

    required_cols: list[str]
    """Input columns that must exist in the DataFrame before compute()."""

    min_periods: int
    """Minimum number of rows required for a valid (non-NaN) output."""

    def compute(self, df: pl.DataFrame) -> pl.Series | pl.DataFrame:
        """Compute the feature from ``df``.

        Args:
            df: Input DataFrame containing at least the columns in
                ``required_cols``, sorted by timestamp ascending.

        Returns:
            A ``pl.Series`` (single feature) or ``pl.DataFrame``
            (multiple related features, columns named accordingly).
            First ``min_periods - 1`` values should be null/NaN.
        """
        ...

    def validate_inputs(self, df: pl.DataFrame) -> None:
        """Validate that ``df`` satisfies this feature's requirements.

        Args:
            df: Input DataFrame to validate.

        Raises:
            ValueError: If any required column is missing or
                ``df.height < min_periods``.
        """
        ...


@runtime_checkable
class FeaturePipeline(Protocol):
    """Protocol for computing a batch of features as a single DataFrame."""

    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute every registered feature and return as wide DataFrame.

        Args:
            df: Input OHLCV DataFrame.

        Returns:
            DataFrame with one column per feature, same row count as ``df``.
        """
        ...


# ---------------------------------------------------------------------------
# Mixin for concrete feature implementations
# ---------------------------------------------------------------------------

class BaseFeature:
    """Optional mixin providing default validate_inputs() for concrete features.

    Concrete classes should inherit this and set class-level ``name``,
    ``version``, ``required_cols``, and ``min_periods``.
    """

    name: str = "base_feature"
    version: str = "1.0"
    required_cols: list[str] = []
    min_periods: int = 1

    def validate_inputs(self, df: pl.DataFrame) -> None:
        """Validate required columns and minimum row count.

        Args:
            df: Input DataFrame to validate.

        Raises:
            ValueError: If required columns are missing or insufficient rows.
        """
        missing = [c for c in self.required_cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"[{self.name}] Missing required columns: {missing}. "
                f"Available: {df.columns}"
            )
        if df.height < self.min_periods:
            raise ValueError(
                f"[{self.name}] Requires at least {self.min_periods} rows, "
                f"got {df.height}."
            )


"""
# Pytest-style unit tests:

def test_base_feature_validate_missing_col() -> None:
    import pytest
    from qtrader.features.base import BaseFeature
    import polars as pl

    class DummyFeature(BaseFeature):
        name = "dummy"
        required_cols = ["close"]
        min_periods = 5

        def compute(self, df: pl.DataFrame) -> pl.Series:
            return df["close"]

    f = DummyFeature()
    with pytest.raises(ValueError, match="Missing required columns"):
        f.validate_inputs(pl.DataFrame({"open": [1.0]}))

def test_base_feature_validate_min_periods() -> None:
    import pytest
    from qtrader.features.base import BaseFeature
    import polars as pl

    class DummyFeature(BaseFeature):
        name = "dummy"
        required_cols = ["close"]
        min_periods = 10

        def compute(self, df: pl.DataFrame) -> pl.Series:
            return df["close"]

    f = DummyFeature()
    with pytest.raises(ValueError, match="Requires at least"):
        f.validate_inputs(pl.DataFrame({"close": [1.0] * 5}))
"""
