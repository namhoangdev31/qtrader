from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

try:
    from hmmlearn.hmm import GaussianHMM
except Exception:
    GaussianHMM = None
__all__ = ["HMMRegimeSmoother"]
NDIM_2D = 2


@dataclass(slots=True)
class HMMRegimeSmoother:
    n_regimes: int = 3
    stay_prob: float = 0.9
    use_hmmlearn: bool = True
    _transition_matrix: np.ndarray = field(init=False, repr=False)
    _current_state: int | None = field(init=False, default=None)
    _hmm: GaussianHMM | None = field(init=False, default=None)
    _is_fitted: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        off_diag_prob = (1.0 - self.stay_prob) / float(self.n_regimes - 1)
        self._transition_matrix = np.full(
            (self.n_regimes, self.n_regimes), off_diag_prob, dtype=float
        )
        np.fill_diagonal(self._transition_matrix, self.stay_prob)

    def fit(self, features: pl.DataFrame, feature_cols: list[str]) -> None:
        if not self.use_hmmlearn:
            self._is_fitted = True
            return
        if GaussianHMM is None:
            raise RuntimeError("hmmlearn is not installed but use_hmmlearn=True was requested.")
        if not feature_cols:
            raise ValueError("feature_cols must be a non-empty list.")
        x = features.select(feature_cols).to_numpy()
        x = np.nan_to_num(x, copy=False)
        self._hmm = GaussianHMM(n_components=self.n_regimes, covariance_type="full")
        self._hmm.fit(x)
        self._is_fitted = True

    def viterbi_decode(self, features: pl.DataFrame, feature_cols: list[str]) -> pl.Series:
        if not self.use_hmmlearn:
            raise RuntimeError("Viterbi decoding requires use_hmmlearn=True.")
        if not self._is_fitted or self._hmm is None:
            raise RuntimeError("HMMRegimeSmoother must be fitted before Viterbi decoding.")
        if not feature_cols:
            raise ValueError("feature_cols must be provided for Viterbi decoding.")
        x = features.select(feature_cols).to_numpy()
        x = np.nan_to_num(x, copy=False)
        (_, states) = self._hmm.decode(x, algorithm="viterbi")
        return pl.Series("regime_viterbi", states.astype(int))

    def smooth_regime(self, raw_probs: np.ndarray) -> int:
        if raw_probs.shape[0] != self.n_regimes:
            raise ValueError("raw_probs length must equal n_regimes.")
        if self._current_state is None:
            self._current_state = int(np.argmax(raw_probs))
            return self._current_state
        posterior = raw_probs * self._transition_matrix[self._current_state]
        self._current_state = int(np.argmax(posterior))
        return self._current_state

    def process_series(self, raw_probs: np.ndarray) -> pl.Series:
        if raw_probs.ndim != NDIM_2D or raw_probs.shape[1] != self.n_regimes:
            raise ValueError("raw_probs must have shape (n_samples, n_regimes).")
        smoothed: list[int] = []
        for row in raw_probs:
            smoothed.append(self.smooth_regime(row))
        return pl.Series("smooth_regime", smoothed)


if __name__ == "__main__":
    _raw = np.array([[0.8, 0.2], [0.7, 0.3], [0.4, 0.6]], dtype=float)
    _smoother = HMMRegimeSmoother(n_regimes=2, stay_prob=0.9, use_hmmlearn=False)
    _series = _smoother.process_series(_raw)
    if len(_series) != _raw.shape[0]:
        raise ValueError("Smoothed series length mismatch")
