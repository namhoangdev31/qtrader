from typing import Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class Feature(Protocol):
    """Protocol for a single feature or technical indicator."""

    @property
    def name(self) -> str:
        ...

    def compute(self, df: pl.DataFrame) -> pl.Series:
        ...


@runtime_checkable
class FeaturePipeline(Protocol):
    """Protocol for computing a batch of features."""

    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame:
        ...
