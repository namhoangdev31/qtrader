from __future__ import annotations

from typing import Any, cast

import numpy as np
import polars as pl

try:
    from hmmlearn.hmm import GaussianHMM
    from numpy import _globals

    if hasattr(_globals, "_CopyMode"):
        _globals._CopyMode.__bool__ = lambda x: True  # type: ignore
except ImportError:
    GaussianHMM = None


class HMMRegimeModel:
    """
    Hidden Markov Model for market regime detection.
    Optimized for returns series to identify Bull, Bear, and Sideways states.
    """

    def __init__(
        self, n_components: int = 3, random_state: int | None = None, covariance_type: str = "full"
    ) -> None:
        """
        Initialize the HMM model.

        Args:
            n_components: Number of hidden regimes.
            random_state: Seed for reproducibility.
            covariance_type: Type of covariance ('full', 'tied', 'diag', 'spherical').
        """
        if GaussianHMM is None:
            raise ImportError(
                "hmmlearn is required for HMMRegimeModel. Install it via pip install hmmlearn."
            )

        self.model = GaussianHMM(
            n_components=n_components,
            covariance_type=covariance_type,
            random_state=random_state,
            n_iter=500,
            tol=1e-6,
        )
        self.n_components = n_components
        self._means: np.ndarray[Any, Any] | None = None
        self._stds: np.ndarray[Any, Any] | None = None
        self._is_fitted: bool = False
        self._state_map: np.ndarray[Any, Any] | None = None

    def _standardize(self, data: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """Standardize features using fitted statistics."""
        if self._means is None or self._stds is None:
            raise RuntimeError("Model stats not initialized. Call fit() first.")

        # Avoid division by zero
        stds_safe = np.where(self._stds == 0.0, 1.0, self._stds)
        return cast(np.ndarray[Any, Any], (data - self._means) / stds_safe)

    def fit(self, df: pl.DataFrame, feature_cols: list[str]) -> None:
        """
        Fit the HMM to the returns series and internalize state mapping.

        Args:
            df: Input Polars DataFrame.
            feature_cols: List of column names used as features.
        """
        if not feature_cols:
            raise ValueError("feature_cols list cannot be empty.")

        x_raw = df.select(feature_cols).to_numpy().astype(np.float64)

        # 1. Compute standardization stats
        self._means = np.mean(x_raw, axis=0)
        self._stds = np.std(x_raw, axis=0)

        # 2. Standardize
        x_std = self._standardize(x_raw)

        # 3. Fit model
        self.model.fit(x_std)

        # 4. Standardize states for interpretability
        # We sort states based on the mean return (first feature by convention)
        state_means = self.model.means_[:, 0]
        self._state_map = np.argsort(state_means)

        self._is_fitted = True

    def predict(self, df: pl.DataFrame, feature_cols: list[str]) -> pl.Series:
        """
        Find the most likely sequence of hidden states (Viterbi).

        Args:
            df: Input Polars DataFrame.
            feature_cols: Feature columns.

        Returns:
            Polars Series of regime labels (Bear=0, Sideways=1, Bull=2).
        """
        if not self._is_fitted:
            raise RuntimeError("Model is not fitted. Call fit() first.")

        x_raw = df.select(feature_cols).to_numpy().astype(np.float64)
        x_std = self._standardize(x_raw)

        # Predict raw hidden states
        raw_states = self.model.predict(x_std)

        # Map raw states to interpretable ones using the state_map
        # raw_states are the original labels from EM algorithm
        # self._state_map[i] tells us which raw state index corresponds to sorted level i
        # We need the inverse mapping: raw_state -> sorted_index
        if self._state_map is None:
            raise RuntimeError("State map not initialized.")

        inverse_map = np.empty_like(self._state_map)
        inverse_map[self._state_map] = np.arange(self.n_components)

        sorted_states = inverse_map[raw_states]

        return pl.Series("regime", sorted_states)

    def predict_proba(self, df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
        """
        Compute posterior probabilities for each hidden state.

        Args:
            df: Input Polars DataFrame.
            feature_cols: Feature columns.

        Returns:
            Polars DataFrame with regime_0_prob, regime_1_prob, etc.
        """
        if not self._is_fitted or self._state_map is None:
            raise RuntimeError("Model is not fitted. Call fit() first.")

        x_raw = df.select(feature_cols).to_numpy().astype(np.float64)
        x_std = self._standardize(x_raw)

        # raw_probs: (N, n_components)
        raw_probs = self.model.predict_proba(x_std)

        # Reorder probabilities based on state_map
        # state_map[i] = raw_index of sorted_state i
        sorted_probs = raw_probs[:, self._state_map]

        cols = [f"regime_{i}_prob" for i in range(self.n_components)]
        return pl.DataFrame(sorted_probs, schema=cols)

    @property
    def transition_matrix(self) -> np.ndarray[Any, Any]:
        """Get the transition probability matrix (reordered)."""
        if not self._is_fitted or self._state_map is None:
            raise RuntimeError("Model is not fitted.")

        matrix = self.model.transmat_
        # Reorder matrix rows and columns based on state_map
        return cast(np.ndarray[Any, Any], matrix[self._state_map][:, self._state_map])

    @property
    def state_means(self) -> np.ndarray[Any, Any]:
        """Get the means of the hidden states (reordered)."""
        if not self._is_fitted or self._state_map is None:
            raise RuntimeError("Model is not fitted.")
        return cast(np.ndarray[Any, Any], self.model.means_[self._state_map])
