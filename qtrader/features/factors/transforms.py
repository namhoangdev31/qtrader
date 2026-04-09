from __future__ import annotations
import math
import polars as pl

__all__ = [
    "cross_sectional_rank",
    "cross_sectional_zscore",
    "exponential_decay_ma",
    "information_coefficient",
    "rolling_zscore",
    "winsorize",
]


def rolling_zscore(series: pl.Series, window: int) -> pl.Series:
    name = series.name or "zscore"
    rolling_mean = series.rolling_mean(window)
    rolling_std = series.rolling_std(window)
    return (
        pl.when(rolling_std == 0.0)
        .then(None)
        .otherwise((series - rolling_mean) / rolling_std)
        .alias(f"{name}_zscore")
    )


def cross_sectional_rank(df: pl.DataFrame, col: str, timestamp_col: str = "timestamp") -> pl.Series:
    if col not in df.columns:
        raise ValueError(f"Column '{col}' not found in DataFrame.")
    if timestamp_col not in df.columns:
        raise ValueError(f"Timestamp column '{timestamp_col}' not found.")
    ranked = pl.col(col).rank(method="average").over(timestamp_col)
    rank_min = pl.col(col).rank(method="average").min().over(timestamp_col)
    rank_max = pl.col(col).rank(method="average").max().over(timestamp_col)
    normalized = (
        pl.when(rank_max == rank_min)
        .then(0.5)
        .otherwise((ranked - rank_min) / (rank_max - rank_min))
    )
    return df.select(normalized.alias(f"{col}_cs_rank"))[f"{col}_cs_rank"]


def exponential_decay_ma(series: pl.Series, halflife: int) -> pl.Series:
    name = series.name or "ema"
    return series.ewm_mean(half_life=halflife, adjust=False).alias(f"{name}_ema{halflife}")


def information_coefficient(predicted: pl.Series, realized: pl.Series) -> float:
    if predicted.len() < 2 or realized.len() < 2:
        return 0.0
    if predicted.len() != realized.len():
        raise ValueError("predicted and realized must have the same length.")
    df_corr = pl.DataFrame({"p": predicted, "r": realized})
    ic = df_corr.select(
        pl.corr(pl.col("p").rank(), pl.col("r").rank(), method="pearson")
    ).to_series()[0]
    return float(ic) if ic is not None and (not math.isnan(ic)) else 0.0


def winsorize(series: pl.Series, lower: float = 0.01, upper: float = 0.99) -> pl.Series:
    lo = series.quantile(lower, interpolation="linear")
    hi = series.quantile(upper, interpolation="linear")
    name = series.name or "winsorized"
    return series.clip(lo, hi).alias(name)


def cross_sectional_zscore(
    df: pl.DataFrame, col: str, timestamp_col: str = "timestamp"
) -> pl.Series:
    mean_expr = pl.col(col).mean().over(timestamp_col)
    std_expr = pl.col(col).std().over(timestamp_col)
    zscore_expr = pl.when(std_expr == 0.0).then(0.0).otherwise((pl.col(col) - mean_expr) / std_expr)
    return df.select(zscore_expr.alias(f"{col}_cs_zscore"))[f"{col}_cs_zscore"]
