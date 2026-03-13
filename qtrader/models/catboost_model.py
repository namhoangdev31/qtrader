from typing import Any

import polars as pl
from catboost import CatBoostRegressor, Pool

from qtrader.models.base import Predictor


class CatBoostPredictor(Predictor):
    """Wrapper for CatBoost model with Polars support."""

    def __init__(self, model_params: dict[str, Any] | None = None) -> None:
        params = model_params or {
            "iterations": 1000,
            "learning_rate": 0.05,
            "depth": 6,
            "loss_function": "MAE",
            "verbose": False,
            "allow_writing_files": False,
        }
        self.model = CatBoostRegressor(**params)

    def train(self, X: pl.DataFrame, y: pl.Series, params: dict[str, Any] | None = None) -> None:
        # Convert Polars to NumPy for CatBoost
        train_pool = Pool(X.to_numpy(), label=y.to_numpy())
        self.model.fit(train_pool)

    def predict(self, X: pl.DataFrame) -> pl.Series:
        preds = self.model.predict(X.to_numpy())
        return pl.Series("predictions", preds)

    def save(self, path: str) -> None:
        self.model.save_model(path)

    def load(self, path: str) -> None:
        self.model.load_model(path)
