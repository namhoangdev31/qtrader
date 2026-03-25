from __future__ import annotations

from typing import Any, cast

import numpy as np
import polars as pl
from sklearn.linear_model import SGDRegressor


class OnlineLearner:
    """
    Online learning implementation using Stochastic Gradient Descent (SGD).
    Manual implementation to ensure maximum stability and zero-dependency
    at the core math level, bypassing environment compatibility issues.
    """

    def __init__(
        self,
        learning_rate: str = "invscaling",
        eta0: float = 0.01,
        power_t: float = 0.25,
        random_state: Optional[int] = None,
    ) -> None:
        """
        Initialize the online learner.

        Args:
            learning_rate: The learning rate schedule (currently supports 'invscaling').
            eta0: The initial learning rate.
            power_t: The exponent for inverse scaling learning rate.
            random_state: Seed for reproducibility (affects initialization).
        """
        self.eta0 = eta0
        self.power_t = power_t
        self.learning_rate = learning_rate
        self.random_state = random_state
        self.weights: Optional[np.ndarray[Any, Any]] = None
        self.bias: float = 0.0
        self.t: int = 0
        self._is_initialized = False

    def update(
        self,
        x_batch: pl.DataFrame | np.ndarray[Any, Any],
        y_batch: pl.Series | np.ndarray[Any, Any],
    ) -> None:
        """
        Incrementally update the model weights using SGD.

        Formula: theta_{t+1} = theta_t - eta * grad(L)
        Where L is the squared error loss.

        Args:
            x_batch: Feature matrix for the current batch.
            y_batch: Target returns for the current batch.
        """
        # Convert polars to numpy if necessary
        x_baked = x_batch.to_numpy() if isinstance(x_batch, pl.DataFrame) else x_batch
        y_baked = y_batch.to_numpy() if isinstance(y_batch, pl.Series) else y_batch

        # Ensure float64
        x_baked = x_baked.astype(np.float64)
        y_baked = y_baked.astype(np.float64)

        n_samples, n_features = x_baked.shape
        if n_samples != y_baked.shape[0]:
            raise ValueError(f"Batch size mismatch: X has {n_samples}, y has {y_baked.shape[0]}")

        # Initialize weights on first update
        if self.weights is None:
            if self.random_state is not None:
                rng = np.random.default_rng(self.random_state)
                self.weights = rng.standard_normal(n_features) * 0.01
            else:
                self.weights = np.zeros(n_features)

        # Stochastic Gradient Descent updates
        for i in range(n_samples):
            self.t += 1
            # Compute current learning rate
            if self.learning_rate == "invscaling":
                eta = self.eta0 / pow(self.t, self.power_t)
            else:
                eta = self.eta0

            xi = x_baked[i]
            yi = y_baked[i]

            # Prediction: y_hat = w . x + b
            y_hat = float(np.dot(xi, self.weights)) + self.bias
            error = y_hat - yi

            # Gradients:
            # dL/dw = error * x
            # dL/db = error
            self.weights -= eta * error * xi
            self.bias -= eta * error

        self._is_initialized = True

    def predict(self, x_data: pl.DataFrame | np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """
        Generate predictions using current weights.

        Args:
            x_data: Feature matrix.

        Returns:
            Predicted returns.
        """
        x_baked = x_data.to_numpy() if isinstance(x_data, pl.DataFrame) else x_data
        x_baked = x_baked.astype(np.float64)

        if not self._is_initialized or self.weights is None:
            return np.zeros(x_baked.shape[0])

        return cast(np.ndarray[Any, Any], np.dot(x_baked, self.weights) + self.bias)

    @property
    def coefficients(self) -> np.ndarray[Any, Any]:
        """Get the current model weights."""
        if self.weights is None:
            return np.array([])
        return self.weights
