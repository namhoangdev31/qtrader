from __future__ import annotations

import polars as pl

MIN_SAMPLES = 2


class SignalAnalyzer:
    @staticmethod
    def compute_ic(df: pl.DataFrame, signal_col: str, return_col: str, lag: int = 1) -> float:
        if df.is_empty():
            return 0.0
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
        decay = {}
        for k in range(1, max_lag + 1):
            decay[k] = SignalAnalyzer.compute_ic(df, signal_col, return_col, lag=k)
        return decay

    @staticmethod
    def compute_rolling_ic(
        df: pl.DataFrame, signal_col: str, return_col: str, window: int, lag: int = 1
    ) -> pl.Series:
        temp_df = df.with_columns(pl.col(return_col).shift(-lag).alias("_target"))
        return temp_df.select(
            [
                pl.rolling_corr(pl.col(signal_col), pl.col("_target"), window_size=window).alias(
                    "rolling_ic"
                )
            ]
        )["rolling_ic"]
