from typing import Any

import polars as pl
import xgboost as xgb

from qtrader.models.base import Predictor


class XGBoostPredictor(Predictor):
    """Wrapper for XGBoost model with Polars support."""

    def __init__(self, model_params: dict[str, Any] | None = None) -> None:
        params = model_params or {
            "n_estimators": 1000,
            "learning_rate": 0.05,
            "max_depth": 6,
            "objective": "reg:absoluteerror",
            "n_jobs": -1,
            "random_state": 42,
        }
        self.model = xgb.XGBRegressor(**params)

    def train(self, X: pl.DataFrame, y: pl.Series, params: dict[str, Any] | None = None) -> None:
        self.model.fit(X.to_numpy(), y.to_numpy())

    def predict(self, X: pl.DataFrame) -> pl.Series:
        preds = self.model.predict(X.to_numpy())
        return pl.Series("predictions", preds)

    def save(self, path: str) -> None:
        self.model.save_model(path)

    def load(self, path: str) -> None:
        self.model.load_model(path)
