"""Feature validation for quantitative factors using vectorized Polars."""
from __future__ import annotations

import polars as pl


class FeatureValidator:
    """
    Feature validation module.

    Computes feature quality metrics (IC, decay rate, stability) and determines
    which features are valid for use in alpha generation.

    The validator:
    - Computes Information Coefficient (IC) between features and forward returns
    - Tracks IC decay over time
    - Assesses feature stability
    - Outputs a validity mask and quality scores

    Attributes:
        ic_lookback: Lookback period for IC calculation.
        ic_threshold: Minimum absolute IC to consider feature valid.
        decay_threshold: Maximum allowed IC decay rate per month.
        stability_lookback: Lookback period for stability calculation.
    """

    def __init__(
        self,
        ic_lookback: int = 20,
        ic_threshold: float = 0.02,
        decay_threshold: float = 0.5,
        stability_lookback: int = 60,
    ) -> None:
        if ic_lookback <= 0:
            raise ValueError("ic_lookback must be positive")
        if ic_threshold < 0:
            raise ValueError("ic_threshold must be non-negative")
        if decay_threshold < 0:
            raise ValueError("decay_threshold must be non-negative")
        if stability_lookback <= 0:
            raise ValueError("stability_lookback must be positive")

        self.ic_lookback = ic_lookback
        self.ic_threshold = ic_threshold
        self.decay_threshold = decay_threshold
        self.stability_lookback = stability_lookback
        self.metrics: dict[str, dict[str, float]] = {}

    def validate(
        self, features: dict[str, pl.Series], forward_returns: pl.Series
    ) -> dict[str, pl.Series]:
        """
        Validate features and return validated features (invalid ones set to zero).

        Args:
            features: Dictionary mapping feature names to their time series.
            forward_returns: Forward returns series for IC calculation.

        Returns:
            Dictionary of validated features (invalid features are Zeroed).
        """
        self.metrics = {}

        if not features:
            return {}

        validated_features = {}
        for name, series in features.items():
            # Compute IC time series
            full_ic_series = self._compute_ic_series(series, forward_returns)

            # Ignore the initial lookback padding
            ic_series = full_ic_series.tail(-self.ic_lookback)
            if ic_series.is_empty():
                ic_series = full_ic_series

            # Compute metrics
            ic_mean = ic_series.mean() if ic_series.len() > 0 else 0.0
            ic_std = ic_series.std() if ic_series.len() > 0 else 0.0
            ic_ir = ic_mean / ic_std if ic_std != 0.0 else 0.0

            decay_rate = self._compute_decay_rate(ic_series)
            stability_score = self._compute_stability_score(ic_series)

            self.metrics[name] = {
                "ic_mean": float(ic_mean or 0.0),
                "ic_ir": float(ic_ir or 0.0),
                "decay_rate": float(decay_rate),
                "stability_score": float(stability_score),
            }

            # Determine validity
            is_valid = (
                abs(ic_mean or 0.0) >= self.ic_threshold
                and abs(decay_rate) <= self.decay_threshold
                and stability_score >= 0.0
            )

            if is_valid:
                validated_features[name] = series
            else:
                validated_features[name] = pl.Series(
                    values=[0.0] * len(series), name=series.name, dtype=pl.Float64
                )

        return validated_features

    def get_metrics(self) -> dict[str, dict[str, float]]:
        """Return cached validation metrics."""
        return self.metrics.copy()

    def _compute_ic_series(
        self, feature: pl.Series, forward_returns: pl.Series
    ) -> pl.Series:
        """Compute rolling IC (Pearson)."""
        df = pl.DataFrame({"feature": feature, "forward_returns": forward_returns})

        # Rolling stats
        f_mean = pl.col("feature").rolling_mean(self.ic_lookback)
        f_std = pl.col("feature").rolling_std(self.ic_lookback)
        r_mean = pl.col("forward_returns").rolling_mean(self.ic_lookback)
        r_std = pl.col("forward_returns").rolling_std(self.ic_lookback)

        covariance = (pl.col("feature") - f_mean) * (pl.col("forward_returns") - r_mean)
        cov_mean = covariance.rolling_mean(self.ic_lookback)

        ic_expr = (
            pl.when((f_std > 0.0) & (r_std > 0.0))
            .then(cov_mean / (f_std * r_std))
            .otherwise(0.0)
            .fill_null(0.0)
        )

        return df.select(ic_expr.alias("ic")).to_series()

    def _compute_decay_rate(self, ic_series: pl.Series) -> float:
        """Compute monthly IC decay rate via linear regression slope."""
        if ic_series.is_empty() or len(ic_series) < 2:
            return 0.0

        n = len(ic_series)
        x = pl.Series(values=list(range(n)), dtype=pl.Float64)
        y = ic_series

        x_mean = x.mean() or 0.0
        y_mean = y.mean() or 0.0

        num = ((x - x_mean) * (y - y_mean)).sum()
        den = ((x - x_mean) ** 2).sum()

        if den == 0.0:
            return 0.0

        slope = num / den
        return float(slope * 21)

    def _compute_stability_score(self, ic_series: pl.Series) -> float:
        """Compute IC stability score via Autocorrelation lag 1."""
        if ic_series.is_empty() or len(ic_series) < 2:
            return 0.0

        ic_lag1 = ic_series.shift(1)
        valid_len = min(len(ic_series), len(ic_lag1)) - 1
        if valid_len <= 0:
            return 0.0

        ic_v = ic_series[1 : valid_len + 1]
        ic_l1v = ic_lag1[1 : valid_len + 1]

        m_ic = ic_v.mean() or 0.0
        m_l1 = ic_l1v.mean() or 0.0

        num = ((ic_v - m_ic) * (ic_l1v - m_l1)).sum()
        den_ic = ((ic_v - m_ic) ** 2).sum()
        den_lag = ((ic_l1v - m_l1) ** 2).sum()

        if den_ic == 0.0 or den_lag == 0.0:
            return 0.0

        return float(num / (den_ic**0.5 * den_lag**0.5))
