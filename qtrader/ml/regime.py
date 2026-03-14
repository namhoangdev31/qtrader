
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import polars as pl
from sklearn.mixture import GaussianMixture

try:
    from hmmlearn.hmm import GaussianHMM
except Exception:  # pragma: no cover - optional dependency
    GaussianHMM = None  # type: ignore[assignment]

__all__ = ["RegimeDetector", "VolatilityRegimeDetector"]

RegimeMethod = Literal["gmm", "hmm", "ensemble"]


@dataclass(slots=True)
class RegimeDetector:
    """Ensemble regime detection using GMM / HMM / ensemble.

    By convention:
      - 0 = Bear
      - 1 = Sideways
      - 2 = Bull

    Features are standardized (z-score) before fitting. The scaler statistics
    are stored on the instance and reused during prediction.

    Args:
        n_regimes: Number of latent regimes.
        method: Detection backend: ``\"gmm\"``, ``\"hmm\"`` or ``\"ensemble\"``.
        random_state: Random seed for deterministic clustering.

    Examples:
        >>> import polars as pl
        >>> df = pl.DataFrame({"ret": [0.01, -0.02, 0.005, 0.003], "vol": [0.02, 0.03, 0.01, 0.015]})
        >>> det = RegimeDetector(n_regimes=2, method="gmm")
        >>> _ = det.fit(df, ["ret", "vol"])
        >>> regimes = det.predict_regime(df, ["ret", "vol"])
        >>> len(regimes) == len(df)
        True
    """

    n_regimes: int = 3
    method: RegimeMethod = "gmm"
    random_state: int = 42
    _gmm: Optional[GaussianMixture] = field(init=False, default=None)
    _hmm: Optional["GaussianHMM"] = field(init=False, default=None)  # type: ignore[name-defined]
    _means: Optional[np.ndarray] = field(init=False, default=None)
    _stds: Optional[np.ndarray] = field(init=False, default=None)
    _is_fitted: bool = field(init=False, default=False)

    def _standardize(self, data: np.ndarray) -> np.ndarray:
        if self._means is None or self._stds is None:
            raise RuntimeError("RegimeDetector scaler statistics are not initialized. Call fit() first.")
        stds_safe = np.where(self._stds == 0.0, 1.0, self._stds)
        return (data - self._means) / stds_safe

    def fit(self, df: pl.DataFrame, feature_cols: list[str]) -> None:
        """Fit the underlying regime model.

        Features are standardized using z-scores before fitting. Standardization
        parameters are stored for use during prediction.

        Args:
            df: Input Polars DataFrame containing features.
            feature_cols: Columns used as regime features.
        """
        if not feature_cols:
            raise ValueError("feature_cols must be a non-empty list.")

        features = df.select(feature_cols).to_numpy()
        features = np.nan_to_num(features, copy=False)

        self._means = features.mean(axis=0)
        self._stds = features.std(axis=0)
        x_std = self._standardize(features)

        # GMM is always available for gmm / ensemble.
        self._gmm = GaussianMixture(
            n_components=self.n_regimes,
            covariance_type="full",
            random_state=self.random_state,
        )
        self._gmm.fit(x_std)

        if self.method in ("hmm", "ensemble"):
            if GaussianHMM is None:
                raise RuntimeError("hmmlearn is not installed but method requires HMM.")
            self._hmm = GaussianHMM(
                n_components=self.n_regimes,
                covariance_type="full",
                random_state=self.random_state,
            )
            self._hmm.fit(x_std)

        self._is_fitted = True

    def _predict_proba_internal(self, df: pl.DataFrame, feature_cols: list[str]) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("RegimeDetector must be fitted before prediction.")
        if not feature_cols:
            raise ValueError("feature_cols must be a non-empty list.")
        features = df.select(feature_cols).to_numpy()
        features = np.nan_to_num(features, copy=False)
        x_std = self._standardize(features)

        if self.method == "gmm":
            if self._gmm is None:
                raise RuntimeError("GMM model is not initialized.")
            return self._gmm.predict_proba(x_std)

        if self.method == "hmm":
            if self._hmm is None:
                raise RuntimeError("HMM model is not initialized.")
            # type: ignore[union-attr]
            return self._hmm.predict_proba(x_std)

        # ensemble: average posterior probabilities from GMM and HMM
        if self._gmm is None or self._hmm is None:
            raise RuntimeError("Both GMM and HMM models are required for ensemble method.")
        proba_gmm = self._gmm.predict_proba(x_std)
        # type: ignore[union-attr]
        proba_hmm = self._hmm.predict_proba(x_std)
        return 0.5 * (proba_gmm + proba_hmm)

    def predict_regime(self, df: pl.DataFrame, feature_cols: list[str]) -> pl.Series:
        """Predict integer regime labels.

        Args:
            df: Polars DataFrame with features.
            feature_cols: Feature column names used during fit.

        Returns:
            Polars Series of integer regime labels.
        """
        proba = self._predict_proba_internal(df, feature_cols)
        labels = np.argmax(proba, axis=1).astype(int)
        return pl.Series("regime", labels)

    def predict_proba(self, df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
        """Predict posterior probabilities for each regime.

        Args:
            df: Polars DataFrame with features.
            feature_cols: Feature column names used during fit.

        Returns:
            Polars DataFrame with columns ``regime_0_prob``, ``regime_1_prob``, ....

        Examples:
            >>> import polars as pl
            >>> df = pl.DataFrame({"ret": [0.01, -0.02], "vol": [0.02, 0.03]})
            >>> det = RegimeDetector(n_regimes=2)
            >>> _ = det.fit(df, ["ret", "vol"])
            >>> proba = det.predict_proba(df, ["ret", "vol"])
            >>> set(proba.columns) == {"regime_0_prob", "regime_1_prob"}
            True
        """
        proba = self._predict_proba_internal(df, feature_cols)
        columns = [f"regime_{i}_prob" for i in range(self.n_regimes)]
        return pl.DataFrame(proba, schema=columns)

    def current_regime_confidence(
        self,
        df: pl.DataFrame,
        feature_cols: list[str],
    ) -> tuple[int, float]:
        """Return the latest regime and its confidence.

        Args:
            df: Polars DataFrame with features.
            feature_cols: Feature column names used during fit.

        Returns:
            Tuple of ``(regime_id, confidence)`` for the most recent row.
        """
        proba_df = self.predict_proba(df, feature_cols)
        if proba_df.height == 0:
            raise ValueError("Input DataFrame is empty.")
        last = proba_df.tail(1)
        probs = np.array([last.select(col).item() for col in last.columns], dtype=float)
        regime_id = int(np.argmax(probs))
        confidence = float(np.max(probs))
        return regime_id, confidence

    def get_regime_stats(self, df: pl.DataFrame, regimes: pl.Series) -> pl.DataFrame:
        """Compute per-regime average return, volatility and Sharpe.

        Expects a ``close`` column to derive simple returns.

        Args:
            df: Price DataFrame containing at least ``close``.
            regimes: Regime labels aligned with ``df`` rows.

        Returns:
            Polars DataFrame with columns:
            ``regime``, ``avg_return``, ``vol``, ``sharpe``, ``count``.
        """
        if "close" not in df.columns:
            raise ValueError("DataFrame must contain a 'close' column for return calculation.")
        if len(df) != len(regimes):
            raise ValueError("regimes length must match df height.")

        df_with_regime = df.with_columns(
            [
                regimes.alias("regime"),
                pl.col("close").pct_change().alias("ret"),
            ]
        )
        grouped = (
            df_with_regime.group_by("regime")
            .agg(
                [
                    pl.col("ret").mean().alias("avg_return"),
                    pl.col("ret").std().alias("vol"),
                    pl.count().alias("count"),
                ]
            )
            .with_columns(
                (
                    pl.col("avg_return")
                    / (pl.col("vol") + 1e-12)
                    * (252.0**0.5)
                ).alias("sharpe")
            )
            .sort("regime")
        )
        return grouped

    def is_transitioning(
        self,
        df: pl.DataFrame,
        feature_cols: list[str],
        window: int = 5,
    ) -> bool:
        """Return True if the regime changed within the last ``window`` bars.

        Args:
            df: Input DataFrame with features.
            feature_cols: Feature column names used during fit.
            window: Lookback window in bars.

        Returns:
            True if a regime change occurred within the window, False otherwise.
        """
        if window <= 0:
            raise ValueError("window must be positive.")
        regimes = self.predict_regime(df, feature_cols)
        if len(regimes) == 0:
            return False
        lookback = min(window, len(regimes))
        recent = regimes.tail(lookback).to_list()
        latest = recent[-1]
        return any(label != latest for label in recent[:-1])


@dataclass(slots=True)
class VolatilityRegimeDetector:
    """Simple volatility-based regime classifier.

    Uses empirical volatility quantiles to label each row as:
      - 0: Low volatility
      - 1: Normal volatility
      - 2: High volatility

    Args:
        low_vol_pct: Quantile below which volatility is considered low.
        high_vol_pct: Quantile above which volatility is considered high.
        lookback: Number of most recent observations used to estimate thresholds.

    Examples:
        >>> import polars as pl
        >>> df = pl.DataFrame({"realized_vol": [0.1, 0.2, 0.3, 0.4]})
        >>> det = VolatilityRegimeDetector()
        >>> regimes = det.classify(df, "realized_vol")
        >>> len(regimes) == len(df)
        True
    """

    low_vol_pct: float = 0.33
    high_vol_pct: float = 0.67
    lookback: int = 252

    def classify(self, df: pl.DataFrame, vol_col: str = "realized_vol") -> pl.Series:
        """Classify rows into volatility regimes.

        Args:
            df: Input DataFrame containing a volatility column.
            vol_col: Name of the volatility column.

        Returns:
            Polars Series of integer labels: 0=Low, 1=Normal, 2=High.
        """
        if vol_col not in df.columns:
            raise ValueError(f"Column '{vol_col}' not found in DataFrame.")
        if df.height == 0:
            return pl.Series("vol_regime", [], dtype=pl.Int64)

        tail_df = df.tail(self.lookback) if df.height > self.lookback else df
        vols = tail_df.select(pl.col(vol_col)).to_series().to_numpy()
        low_thr = float(np.quantile(vols, self.low_vol_pct))
        high_thr = float(np.quantile(vols, self.high_vol_pct))

        regimes = (
            df.select(
                pl.when(pl.col(vol_col) <= low_thr)
                .then(0)
                .when(pl.col(vol_col) >= high_thr)
                .then(2)
                .otherwise(1)
                .alias("vol_regime")
            )
            .to_series()
        )
        return regimes


if __name__ == "__main__":
    # Minimal smoke test examples (pytest-style)
    import polars as pl  # type: ignore[reimported]

    _df = pl.DataFrame({"ret": [0.01, -0.02, 0.003], "vol": [0.02, 0.03, 0.015]})
    _det = RegimeDetector(n_regimes=2, method="gmm")
    _det.fit(_df, ["ret", "vol"])
    _reg = _det.predict_regime(_df, ["ret", "vol"])
    assert len(_reg) == _df.height

    _vol_det = VolatilityRegimeDetector()
    _vol_reg = _vol_det.classify(pl.DataFrame({"realized_vol": [0.1, 0.2, 0.3]}))
    assert set(_vol_reg.to_list()) <= {0, 1, 2}

