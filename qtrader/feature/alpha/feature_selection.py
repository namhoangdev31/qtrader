from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sklearn.feature_selection import mutual_info_regression

from qtrader.feature.alpha.ic import SignalAnalyzer

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    import polars as pl

MIN_MI_SAMPLES = 5


class FeatureSelector:
    """
    Selects statistically significant features based on IC, Stability, and MI.
    """

    def __init__(
        self,
        ic_threshold: float = 0.02,
        stability_threshold: float = 0.05,
        mi_threshold: float = 0.01,
        window: int = 252,
    ) -> None:
        """
        Args:
            ic_threshold: Minimum absolute IC magnitude.
            stability_threshold: Maximum IC standard deviation over time.
            mi_threshold: Minimum Mutual Information score.
            window: Lookback for rolling IC stability.
        """
        self.ic_threshold = ic_threshold
        self.stability_threshold = stability_threshold
        self.mi_threshold = mi_threshold
        self.window = window

    def select_features(
        self, df: pl.DataFrame, feature_cols: list[str], target_col: str, top_k: int = 10
    ) -> list[str]:
        """
        Run the feature selection pipeline.

        Args:
            df: DataFrame containing features and target.
            feature_cols: List of candidate feature names.
            target_col: Target return column.
            top_k: Number of features to retain after ranking.

        Returns:
            List of selected feature names.
        """
        if df.is_empty() or not feature_cols:
            return []

        # 1. Compute IC and Stability
        valid_features: list[tuple[str, float, float]] = []
        for feature in feature_cols:
            ic_mean, ic_std = self._compute_ic_stats(df, feature, target_col)

            if abs(ic_mean) > self.ic_threshold and ic_std < self.stability_threshold:
                valid_features.append((feature, ic_mean, ic_std))

        if not valid_features:
            return []

        surviving_cols = [f[0] for f in valid_features]
        mi_scores = self._compute_mi(df, surviving_cols, target_col)

        selected_with_mi = [
            (feat, ic_m, ic_s, mi_scores[feat])
            for feat, ic_m, ic_s in valid_features
            if mi_scores[feat] > self.mi_threshold
        ]

        selected_with_mi.sort(key=lambda x: abs(x[1]) * x[3], reverse=True)

        return [x[0] for x in selected_with_mi[:top_k]]

    def _compute_ic_stats(self, df: pl.DataFrame, feature: str, target: str) -> tuple[float, float]:
        """Compute mean IC and IC volatility."""
        rolling_ic = SignalAnalyzer.compute_rolling_ic(df, feature, target, window=self.window)
        clean_ic = rolling_ic.drop_nulls()

        mean_val = clean_ic.mean()
        std_val = clean_ic.std()

        return (
            cast("float", mean_val) if mean_val is not None else 0.0,
            cast("float", std_val) if std_val is not None else 1.0,
        )

    def _compute_mi(self, df: pl.DataFrame, features: list[str], target: str) -> dict[str, float]:
        data = df.select([*features, target]).drop_nulls()
        if data.height < MIN_MI_SAMPLES:
            return {f: 0.0 for f in features}

        x_matrix = data.select(features).to_numpy()
        y_vector = data.select(target).to_numpy().flatten()

        mi_values: npt.NDArray[np.float64] = mutual_info_regression(
            x_matrix, y_vector, random_state=42
        )

        return {feat: float(score) for feat, score in zip(features, mi_values, strict=True)}
