from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import polars as pl
from typing import ClassVar

__all__ = ["Feature", "FeaturePipeline"]


@runtime_checkable
class Feature(Protocol):
    name: str
    version: str
    required_cols: list[str]
    min_periods: int

    def compute(self, df: pl.DataFrame) -> pl.Series | pl.DataFrame: ...

    def validate_inputs(self, df: pl.DataFrame) -> None: ...
        pass


@runtime_checkable
class FeaturePipeline(Protocol):
    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame: ...
        pass


class BaseFeature:
    name: ClassVar[str] = "base_feature"
    version: ClassVar[str] = "1.0"
    required_cols: ClassVar[list[str]] = []
    min_periods: ClassVar[int] = 1

    def validate_inputs(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.required_cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"[{self.name}] Missing required columns: {missing}. Available: {df.columns}"
            )
        if df.height < self.min_periods:
            raise ValueError(
                f"[{self.name}] Requires at least {self.min_periods} rows, got {df.height}."
            )
