from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import polars as pl

_LOG = logging.getLogger("qtrader.ml.online_learning")


@dataclass(slots=True)
class LearningReport:
    """
    Industrial Telemetry for Model Adaptation.
    """

    status: str
    action: str
    performance_gain: float
    promotion_authorized: bool


class ReplayBuffer:
    """
    Industrial Replay Buffer for Online Learning.

    Objective: Prevent 'Catastrophic Forgetting' by storing and sampling
    recent market transitions for out-of-sample validation and batch replay.
    """

    def __init__(self, capacity: int = 1000) -> None:
        """
        Initialize the buffer with a fixed absolute capacity.
        """
        self._capacity = capacity
        self._buffer: list[tuple[np.ndarray[Any, Any], float]] = []

    def push(self, x: np.ndarray[Any, Any], y: float) -> None:
        """
        Push a new transition into the buffer. Evicts oldest if at capacity.
        """
        self._buffer.append((x, y))
        if len(self._buffer) > self._capacity:
            self._buffer.pop(0)

    def sample(self, batch_size: int) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        """
        Randomly sample transitions from the buffer.
        """
        if not self._buffer:
            return np.array([]), np.array([])

        size = min(len(self._buffer), batch_size)
        indices = np.random.choice(len(self._buffer), size, replace=False)

        x_samples = np.stack([self._buffer[i][0] for i in indices])
        y_samples = np.array([self._buffer[i][1] for i in indices])
        return x_samples, y_samples

    @property
    def size(self) -> int:
        """Current number of transitions in the buffer."""
        return len(self._buffer)


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
        random_state: int | None = None,
    ) -> None:
        """
        Initialize the online learner.
        """
        self.eta0 = eta0
        self.power_t = power_t
        self.learning_rate = learning_rate
        self.random_state = random_state
        self.weights: np.ndarray[Any, Any] | None = None
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
        """
        x_baked = x_batch.to_numpy() if isinstance(x_batch, pl.DataFrame) else x_batch
        y_baked = y_batch.to_numpy() if isinstance(y_batch, pl.Series) else y_batch

        x_baked = x_baked.astype(np.float64)
        y_baked = y_baked.astype(np.float64)

        if len(x_baked.shape) == 1:
            x_baked = x_baked.reshape(1, -1)

        n_samples, n_features = x_baked.shape

        if self.weights is None:
            if self.random_state is not None:
                rng = np.random.default_rng(self.random_state)
                self.weights = rng.standard_normal(n_features) * 0.01
            else:
                self.weights = np.zeros(n_features)

        for i in range(n_samples):
            self.t += 1
            eta = (
                self.eta0 / pow(self.t, self.power_t)
                if self.learning_rate == "invscaling"
                else self.eta0
            )

            xi = x_baked[i]
            yi = float(y_baked[i])

            y_hat = float(np.dot(xi, self.weights)) + self.bias
            error = y_hat - yi

            self.weights -= eta * error * xi
            self.bias -= eta * error

        self._is_initialized = True

    def predict(self, x_data: pl.DataFrame | np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """
        Generate predictions using current weights.
        """
        x_baked = x_data.to_numpy() if isinstance(x_data, pl.DataFrame) else x_data
        x_baked = x_baked.astype(np.float64)

        if not self._is_initialized or self.weights is None:
            return np.zeros(x_baked.shape[0])

        if len(x_baked.shape) == 1:
            x_baked = x_baked.reshape(1, -1)

        return cast("np.ndarray[Any, Any]", np.dot(x_baked, self.weights) + self.bias)

    @property
    def coefficients(self) -> np.ndarray[Any, Any]:
        """Get the current model weights."""
        return self.weights if self.weights is not None else np.array([])


class SafeOnlineLearningEngine:
    """
    Principal Controlled Learning Engine.

    Objective: Adapt model parameters incrementally under strict validation.
    Enforces zero-trust promotion: theta_new is ONLY deployed if it
    outperforms theta_old on out-of-sample data sampled from the replay buffer.
    """

    def __init__(
        self,
        max_alpha: float = 0.05,
        min_performance_gain: float = 1e-6,
    ) -> None:
        """
        Initialize the Safe Learning Engine.
        """
        self._max_alpha = max_alpha
        self._min_gain = min_performance_gain
        self._stats = {"promotions": 0, "rejections": 0}

    def generate_candidate(
        self, model: OnlineLearner, buffer: ReplayBuffer, batch_size: int = 32
    ) -> OnlineLearner:
        """
        Produce a candidate theta_new using incremental SGD on replay data.
        """
        # 1. Non-destructive cloning (Air-gap from production model)
        candidate = cast("OnlineLearner", pickle.loads(pickle.dumps(model)))  # noqa: S301

        # 2. Controlled Gradient Update
        x_batch, y_batch = buffer.sample(batch_size)
        if x_batch.size > 0:
            candidate.update(x_batch, y_batch)

        return candidate

    def validate_and_promote(
        self,
        old_model: OnlineLearner,
        new_model: OnlineLearner,
        validation_data: tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]],
    ) -> LearningReport:
        """
        Terminal Zero-Trust validation gate for model promotion.
        """
        x_val, y_val = validation_data

        pred_old = old_model.predict(x_val)
        pred_new = new_model.predict(x_val)

        mse_old = float(np.mean((pred_old - y_val) ** 2))
        mse_new = float(np.mean((pred_new - y_val) ** 2))

        gain = mse_old - mse_new

        if gain > self._min_gain:
            self._stats["promotions"] += 1
            _LOG.info(f"LEARNING | PROMOTED | Gain: {gain:.8f}")
            return LearningReport(
                status="LEARNING_SUCCESS",
                action="PROMOTE",
                performance_gain=round(gain, 8),
                promotion_authorized=True,
            )

        self._stats["rejections"] += 1
        return LearningReport(
            status="LEARNING_REJECTED",
            action="RETAIN_OLD",
            performance_gain=round(gain, 8),
            promotion_authorized=False,
        )
