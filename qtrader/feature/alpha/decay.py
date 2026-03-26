from __future__ import annotations

import polars as pl

from qtrader.feature.alpha.ic import SignalAnalyzer


class AlphaDecayDetector:
    """
    Monitors alpha signal health and detects predictive power degradation.

    Mathematical Model:
    - mu_t = mean(IC_{t-k:t})
    - decay_flag = mu_t < threshold
    """

    @staticmethod
    def is_decaying(rolling_ic: pl.Series, threshold: float = 0.01) -> bool:
        """
        Check if the current rolling mean IC indicates alpha decay.

        Args:
            rolling_ic: Series of Information Coefficient values.
            threshold: Minimum acceptable mean IC.

        Returns:
            True if signal is decaying, False otherwise.
        """
        if rolling_ic.is_empty():
            return False

        # Drop nulls caused by lags/rolling windows to get the latest valid mean
        clean_mu = rolling_ic.drop_nulls()

        if clean_mu.is_empty():
            return False

        current_mu = clean_mu.tail(1).item()

        return float(current_mu) < threshold

    @staticmethod
    def check_signal_health(
        df: pl.DataFrame,
        signal_col: str,
        return_col: str,
        monitoring_params: dict[str, float | int] | None = None,
    ) -> bool:
        """
        Full pipeline to detect signal degradation from raw data.

        Args:
            df: DataFrame containing signal and returns.
            signal_col: Alpha signal column.
            return_col: Return column.
            monitoring_params: Optional dict with 'window', 'threshold', 'lag'.

        Returns:
            Decay flag.
        """
        if df.is_empty():
            return True  # Conservative: disable if no data

        params = monitoring_params or {}
        window = int(params.get("window", 252))
        threshold = float(params.get("threshold", 0.01))
        lag = int(params.get("lag", 1))

        # 1. Compute rolling IC
        rolling_ic = SignalAnalyzer.compute_rolling_ic(
            df, signal_col, return_col, window=window, lag=lag
        )

        # 2. Compute rolling mean of the IC
        # Note: compute_rolling_ic returns a series of correlation values.
        # We need the mean of these values to detect trend decay.
        ic_mu = rolling_ic.rolling_mean(window_size=window)

        return AlphaDecayDetector.is_decaying(ic_mu, threshold=threshold)
