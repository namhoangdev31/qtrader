from __future__ import annotations

from typing import TYPE_CHECKING, Any

import lightgbm as lgb
import polars as pl
from scipy.stats import pearsonr
from sklearn.metrics import mean_squared_error

if TYPE_CHECKING:
    import numpy as np


class GBDTAlphaModel:
    """
    Gradient Boosted Decision Tree (GBDT) model for nonlinear alpha forecasting.
    Uses LightGBM for efficient training and inference.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        learning_rate: float = 0.1,
        max_depth: int = -1,
        random_state: int = 42,
    ) -> None:
        """
        Initialize the GBDT model.

        Args:
            n_estimators: Number of boosting iterations.
            learning_rate: Step size shrinkage.
            max_depth: Maximum tree depth (-1 for no limit).
            random_state: Random seed for reproducibility.
        """
        self.model = lgb.LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            random_state=random_state,
            importance_type="gain",
            verbosity=-1,
        )

    def fit(
        self, x_data: pl.DataFrame | np.ndarray[Any, Any], y: pl.Series | np.ndarray[Any, Any]
    ) -> None:
        """
        Train the GBDT model.

        Args:
            x_data: Feature matrix.
            y: Target returns.
        """
        x_baked = x_data.to_numpy() if isinstance(x_data, pl.DataFrame) else x_data
        y_baked = y.to_numpy() if isinstance(y, pl.Series) else y

        self.model.fit(x_baked, y_baked)

    def predict(self, x_data: pl.DataFrame | np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """
        Generate return forecasts.

        Args:
            x_data: Feature matrix.

        Returns:
            Predicted returns.
        """
        x_baked = x_data.to_numpy() if isinstance(x_data, pl.DataFrame) else x_data
        prediction: np.ndarray[Any, Any] = self.model.predict(x_baked)
        return prediction

    def evaluate(
        self,
        x_data: pl.DataFrame | np.ndarray[Any, Any],
        y: pl.Series | np.ndarray[Any, Any],
    ) -> dict[str, float]:
        """
        Evaluate model performance.

        Args:
            x_data: Feature matrix.
            y: True returns.

        Returns:
            Dictionary with MSE and IC.
        """
        y_true = y.to_numpy() if isinstance(y, pl.Series) else y
        y_pred = self.predict(x_data)

        mse = float(mean_squared_error(y_true, y_pred))
        ic, _ = pearsonr(y_true, y_pred)

        return {"mse": mse, "ic": float(ic)}
