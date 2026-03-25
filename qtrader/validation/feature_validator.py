from __future__ import annotations

import polars as pl
from typing import Dict


class FeatureValidator:
    """
    Feature validation module.

    Computes feature quality metrics (IC, decay rate, stability) and determines
    which features are valid for use in strategy generation.

    The validator:
    - Computes Information Coefficient (IC) between features and forward returns
    - Tracks IC decay over time
    - Assesses feature stability
    - Outputs a validity mask and quality scores

    Args:
        ic_lookback: Lookback period for IC calculation (default 20)
        ic_threshold: Minimum absolute IC to consider feature valid (default 0.02)
        decay_threshold: Maximum allowed IC decay rate per month (default 0.5)
        stability_lookback: Lookback period for stability calculation (default 60)
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
        self.metrics: Dict[str, Dict[str, float]] = {}

    def validate(
        self, features: Dict[str, pl.Series], forward_returns: pl.Series
    ) -> Dict[str, pl.Series]:
        """
        Validate features and return validated features (invalid ones set to zero).

        Args:
            features: Dictionary mapping feature names to their time series.
            forward_returns: Forward returns series for IC calculation.

        Returns:
            Dictionary of validated features (same keys as input, but invalid features
            are set to zero series).
        """
        # Reset metrics
        self.metrics = {}
        
        if not features:
            return {}
        
        # Validate each feature
        validated_features = {}
        for name, series in features.items():
            # Compute IC time series
            full_ic_series = self._compute_ic_series(series, forward_returns)
            
            # Use only valid elements for metrics (ignore the initial lookback padding)
            ic_series = full_ic_series.tail(-self.ic_lookback)
            if ic_series.is_empty():
                ic_series = full_ic_series
            
            # Compute metrics
            ic_mean = ic_series.mean() if ic_series.len() > 0 else 0.0
            ic_std = ic_series.std() if ic_series.len() > 0 else 0.0
            ic_ir = ic_mean / ic_std if ic_std != 0.0 else 0.0
            
            decay_rate = self._compute_decay_rate(ic_series)
            stability_score = self._compute_stability_score(ic_series)
            
            # Store metrics
            self.metrics[name] = {
                "ic_mean": float(ic_mean),
                "ic_ir": float(ic_ir),
                "decay_rate": float(decay_rate),
                "stability_score": float(stability_score),
            }
            
            # Determine if feature is valid
            is_valid = (
                abs(ic_mean) >= self.ic_threshold and
                abs(decay_rate) <= self.decay_threshold and
                stability_score >= 0.0  # Stability should be positive (mean reverting or stable)
            )
            
            # If valid, keep the original series; otherwise, set to zero
            if is_valid:
                validated_features[name] = series
            else:
                # Create a zero series of the same length and dtype
                validated_features[name] = pl.Series(
                    values=[0.0] * len(series), name=series.name, dtype=pl.Float64
                )
        
        return validated_features

    def get_metrics(self) -> Dict[str, Dict[str, float]]:
        """
        Get the validation metrics for each feature.

        Returns:
            Dictionary mapping feature names to their metrics (ic_mean, ic_ir, decay_rate, stability_score).
        """
        return self.metrics.copy()

    def _compute_ic_series(self, feature: pl.Series, forward_returns: pl.Series) -> pl.Series:
        """
        Compute the IC (Information Coefficient) time series for a feature.

        Args:
            feature: Feature time series.
            forward_returns: Forward returns time series.

        Returns:
            pl.Series of IC values over time.
        """
        # Create a temporary DataFrame with the two series
        df = pl.DataFrame({
            "feature": feature,
            "forward_returns": forward_returns
        })
        
        # Calculate rolling mean and std for both series
        feature_mean = pl.col("feature").rolling_mean(window_size=self.ic_lookback, min_samples=self.ic_lookback)
        feature_std = pl.col("feature").rolling_std(window_size=self.ic_lookback, min_samples=self.ic_lookback)
        returns_mean = pl.col("forward_returns").rolling_mean(window_size=self.ic_lookback, min_samples=self.ic_lookback)
        returns_std = pl.col("forward_returns").rolling_std(window_size=self.ic_lookback, min_samples=self.ic_lookback)
        
        # Calculate rolling covariance
        covariance = (pl.col("feature") - feature_mean) * (pl.col("forward_returns") - returns_mean)
        covariance_mean = covariance.rolling_mean(window_size=self.ic_lookback, min_samples=self.ic_lookback)
        
        # Calculate rolling correlation (Pearson)
        # Avoid division by zero and handle nulls from small windows
        feature_std_val = feature_std.fill_null(0.0)
        returns_std_val = returns_std.fill_null(0.0)
        
        ic_series_expr = pl.when(
            (feature_std_val > 0.0) & (returns_std_val > 0.0)
        ).then(
            covariance_mean / (feature_std * returns_std)
        ).otherwise(0.0).fill_null(0.0)
        
        # Select the IC series as a new column and then extract it as a Series
        ic_series = df.select(ic_series_expr.alias("ic")).to_series()
        
        return ic_series
    
    def _compute_decay_rate(self, ic_series: pl.Series) -> float:
        """
        Compute the decay rate of IC over time.

        Args:
            ic_series: pl.Series of IC values.

        Returns:
            Decay rate (slope of IC over time). Negative values indicate decay.
        """
        if ic_series.is_empty() or len(ic_series) < 2:
            return 0.0
        
        # Simple linear regression to get slope
        n = len(ic_series)
        x = pl.Series(values=list(range(n)), dtype=pl.Float64)
        y = ic_series
        
        # Calculate means
        x_mean = x.mean()
        y_mean = y.mean()
        
        # Calculate slope: sum((x_i - x_mean)(y_i - y_mean)) / sum((x_i - x_mean)^2)
        numerator = ((x - x_mean) * (y - y_mean)).sum()
        denominator = ((x - x_mean) ** 2).sum()
        
        if denominator == 0.0:
            return 0.0
            
        slope = numerator / denominator
        
        # Convert to monthly decay rate (assuming 252 trading days per year, 21 per month)
        monthly_decay = slope * 21  # Approximate trading days per month
        
        return float(monthly_decay)
    
    def _compute_stability_score(self, ic_series: pl.Series) -> float:
        """
        Compute the stability score of IC (autocorrelation at lag 1).

        Args:
            ic_series: pl.Series of IC values.

        Returns:
            Stability score (autocorrelation at lag 1). Higher values indicate more stability.
        """
        if ic_series.is_empty() or len(ic_series) < 2:
            return 0.0
        
        # Calculate autocorrelation at lag 1
        ic_lag1 = ic_series.shift(1)
        # Drop the first element which will be null due to shift
        valid_length = min(len(ic_series), len(ic_lag1)) - 1
        if valid_length <= 0:
            return 0.0
        
        ic_valid = ic_series[1:valid_length+1]  # Skip first element
        ic_lag1_valid = ic_lag1[1:valid_length+1]  # Skip first element
        
        # Calculate correlation
        mean_ic = ic_valid.mean()
        mean_lag1 = ic_lag1_valid.mean()
        
        if mean_ic is None or mean_lag1 is None:
            return 0.0
            
        numerator = ((ic_valid - mean_ic) * (ic_lag1_valid - mean_lag1)).sum()
        denominator_ic = ((ic_valid - mean_ic) ** 2).sum()
        denominator_lag1 = ((ic_lag1_valid - mean_lag1) ** 2).sum()
        
        if denominator_ic == 0.0 or denominator_lag1 == 0.0:
            return 0.0
            
        autocorr = numerator / (denominator_ic ** 0.5 * denominator_lag1 ** 0.5)
        
        return float(autocorr) if autocorr is not None else 0.0