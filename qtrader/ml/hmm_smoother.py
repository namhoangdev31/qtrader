
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import polars as pl

try:
    from hmmlearn.hmm import GaussianHMM
except Exception:  # pragma: no cover - optional dependency
    GaussianHMM = None  # type: ignore[assignment]

__all__ = ["HMMRegimeSmoother"]


@dataclass(slots=True)
class HMMRegimeSmoother:
    """HMM-based regime smoother with optional Viterbi decoding.

    Two operation modes:
      * ``use_hmmlearn=True``: use a fitted ``GaussianHMM`` and its built-in Viterbi.
      * ``use_hmmlearn=False``: use a simple transition-matrix-based smoother that
        consumes per-regime observation probabilities.

    Args:
        n_regimes: Number of latent regimes.
        stay_prob: Prior probability of remaining in the same regime.
        use_hmmlearn: Whether to use ``hmmlearn``'s ``GaussianHMM`` backend.

    Examples:
        >>> import numpy as np
        >>> import polars as pl
        >>> raw = np.array([[0.7, 0.3], [0.6, 0.4], [0.2, 0.8]])
        >>> smoother = HMMRegimeSmoother(n_regimes=2, stay_prob=0.9, use_hmmlearn=False)
        >>> series = smoother.process_series(raw)
        >>> len(series) == raw.shape[0]
        True
    """

    n_regimes: int = 3
    stay_prob: float = 0.90
    use_hmmlearn: bool = True
    _transition_matrix: np.ndarray = field(init=False, repr=False)
    _current_state: Optional[int] = field(init=False, default=None)
    _hmm: Optional["GaussianHMM"] = field(init=False, default=None)  # type: ignore[name-defined]
    _is_fitted: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        off_diag_prob = (1.0 - self.stay_prob) / float(self.n_regimes - 1)
        self._transition_matrix = np.full(
            (self.n_regimes, self.n_regimes),
            off_diag_prob,
            dtype=float,
        )
        np.fill_diagonal(self._transition_matrix, self.stay_prob)

    def fit(self, features: pl.DataFrame, feature_cols: list[str]) -> None:
        """Fit a GaussianHMM on standardized features if ``use_hmmlearn`` is True.

        Args:
            features: Input feature DataFrame.
            feature_cols: Columns to use as HMM emissions.
        """
        if not self.use_hmmlearn:
            # Only transition matrix smoothing will be used.
            self._is_fitted = True
            return

        if GaussianHMM is None:
            raise RuntimeError("hmmlearn is not installed but use_hmmlearn=True was requested.")
        if not feature_cols:
            raise ValueError("feature_cols must be a non-empty list.")

        x = features.select(feature_cols).to_numpy()
        x = np.nan_to_num(x, copy=False)
        self._hmm = GaussianHMM(
            n_components=self.n_regimes,
            covariance_type="full",
        )
        self._hmm.fit(x)
        self._is_fitted = True

    def viterbi_decode(self, features: pl.DataFrame, feature_cols: list[str]) -> pl.Series:
        """Run Viterbi algorithm for the globally optimal state sequence.

        Args:
            features: Input feature DataFrame.
            feature_cols: Columns to use as HMM emissions.

        Returns:
            Polars Series of smoothed regime labels (integers).
        """
        if not self.use_hmmlearn:
            raise RuntimeError("Viterbi decoding requires use_hmmlearn=True.")
        if not self._is_fitted or self._hmm is None:
            raise RuntimeError("HMMRegimeSmoother must be fitted before Viterbi decoding.")
        if not feature_cols:
            raise ValueError("feature_cols must be provided for Viterbi decoding.")

        x = features.select(feature_cols).to_numpy()
        x = np.nan_to_num(x, copy=False)
        # type: ignore[union-attr]
        _, states = self._hmm.decode(x, algorithm="viterbi")
        return pl.Series("regime_viterbi", states.astype(int))

    def smooth_regime(self, raw_probs: np.ndarray) -> int:
        """Single-step smoothing given per-regime observation probabilities.

        This uses a Viterbi-lite update with the internal transition matrix
        and is intended for real-time processing.

        Args:
            raw_probs: Per-regime observation probabilities for the current bar.

        Returns:
            Integer regime label after smoothing.
        """
        if raw_probs.shape[0] != self.n_regimes:
            raise ValueError("raw_probs length must equal n_regimes.")

        if self._current_state is None:
            self._current_state = int(np.argmax(raw_probs))
            return self._current_state

        posterior = raw_probs * self._transition_matrix[self._current_state]
        self._current_state = int(np.argmax(posterior))
        return self._current_state

    def process_series(self, raw_probs: np.ndarray) -> pl.Series:
        """Process a sequence of observation probabilities into smooth regimes.

        Args:
            raw_probs: Array of shape (n_samples, n_regimes) with observation probabilities.

        Returns:
            Polars Series of integer smoothed regime labels.
        """
        if raw_probs.ndim != 2 or raw_probs.shape[1] != self.n_regimes:
            raise ValueError("raw_probs must have shape (n_samples, n_regimes).")
        smoothed: list[int] = []
        for row in raw_probs:
            smoothed.append(self.smooth_regime(row))
        return pl.Series("smooth_regime", smoothed)


if __name__ == "__main__":
    _raw = np.array([[0.8, 0.2], [0.7, 0.3], [0.4, 0.6]], dtype=float)
    _smoother = HMMRegimeSmoother(n_regimes=2, stay_prob=0.9, use_hmmlearn=False)
    _series = _smoother.process_series(_raw)
    assert len(_series) == _raw.shape[0]

