from __future__ import annotations

import polars as pl

MIN_SAMPLES = 2


class SignalAnalyzer:
    """
    Measurement tools for Alpha Signal predictive power (IC/Rank IC).

    Formula:
    - IC(k) = corr(signal_t, return_{t+k})
    """

    @staticmethod
    def compute_ic(df: pl.DataFrame, signal_col: str, return_col: str, lag: int = 1) -> float:
        """
        Compute Information Coefficient (Pearson Correlation) for a specific lag.

        Args:
            df: DataFrame containing signal and returns.
            signal_col: Name of the alpha signal column.
            return_col: Name of the raw return column.
            lag: Future return offset (t + lag).

        Returns:
            Pearson IC value.
        """
        if df.is_empty():
            return 0.0

        # Shift target return back to align with signal at t
        # Or shift signal forward? Standard is signal_t vs return_{t+lag}
        temp_df = df.select(
            [pl.col(signal_col), pl.col(return_col).shift(-lag).alias("target_return")]
        ).drop_nulls()

        if temp_df.height < MIN_SAMPLES:
            return 0.0

        return float(temp_df.select(pl.corr(signal_col, "target_return")).item(0, 0))

    @staticmethod
    def compute_ic_decay(
        df: pl.DataFrame, signal_col: str, return_col: str, max_lag: int = 10
    ) -> dict[int, float]:
        """
        Compute IC decay curve over multiple lags.

        Args:
            df: DataFrame containing signal and returns.
            signal_col: Name of the alpha signal column.
            return_col: Name of the raw return column.
            max_lag: Maximum lag to compute.

        Returns:
            Dictionary mapping lag to IC value.
        """
        decay = {}
        for k in range(1, max_lag + 1):
            decay[k] = SignalAnalyzer.compute_ic(df, signal_col, return_col, lag=k)

        return decay

    @staticmethod
    def compute_rolling_ic(
        df: pl.DataFrame, signal_col: str, return_col: str, window: int, lag: int = 1
    ) -> pl.Series:
        """
        Compute rolling IC over a specific window.

        Args:
            df: DataFrame containing signal and returns.
            signal_col: Name of the signal column.
            return_col: Name of the return column.
            window: Rolling window size.
            lag: Future return offset.

        Returns:
            Series of rolling IC values.
        """
        # Align data first
        temp_df = df.with_columns(pl.col(return_col).shift(-lag).alias("_target"))

        # Pearson correlation: cov(x,y) / (std(x) * std(y))
        # Polars rolling_corr exists for Expr but requires alignment
        return temp_df.select(
            [
                pl.rolling_corr(pl.col(signal_col), pl.col("_target"), window_size=window).alias(
                    "rolling_ic"
                )
            ]
        )["rolling_ic"]
