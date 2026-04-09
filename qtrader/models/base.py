from typing import Any, Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class Predictor(Protocol):
    """Protocol for ML prediction models (CatBoost, XGBoost, etc.)."""

    def train(
        self, X: pl.DataFrame, y: pl.Series, params: dict[str, Any] | None = None
    ) -> None: ...

    def predict(self, X: pl.DataFrame) -> pl.Series: ...

    def save(self, path: str) -> None: ...

    def load(self, path: str) -> None: ...
