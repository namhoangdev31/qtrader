"""Statistical transforms and signal-quality utilities.

All functions operate on Polars Series/DataFrames.
No numpy loops, no row-by-row Python iteration.
"""

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
    """Rolling Z-score: (x - rolling_mean) / rolling_std.

    Args:
        series: Input series (numeric).
        window: Look-back window in periods.

    Returns:
        Z-scored series; first ``window - 1`` values are null.

    Example::

        s = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z = rolling_zscore(s, window=3)
    """
    name = series.name or "zscore"
    rolling_mean = series.rolling_mean(window)
    rolling_std = series.rolling_std(window)
    return (
        pl.when(rolling_std == 0.0)
        .then(None)
        .otherwise((series - rolling_mean) / rolling_std)
        .alias(f"{name}_zscore")
    )


def cross_sectional_rank(
    df: pl.DataFrame,
    col: str,
    timestamp_col: str = "timestamp",
) -> pl.Series:
    """Rank assets by ``col`` within each timestamp, normalized to [0, 1].

    Args:
        df: Long-format DataFrame with ``timestamp_col`` and ``col``.
        col: Column to rank.
        timestamp_col: Column identifying the cross-sectional time slice.

    Returns:
        Normalized rank series in [0, 1]; higher value = higher rank.

    Example::

        df = pl.DataFrame({"timestamp": ["t1","t1","t1"], "signal": [0.1, 0.5, 0.3]})
        ranks = cross_sectional_rank(df, "signal")
        # → [0.0, 1.0, 0.5] (min-max after rank)
    """
    if col not in df.columns:
        raise ValueError(f"Column '{col}' not found in DataFrame.")
    if timestamp_col not in df.columns:
        raise ValueError(f"Timestamp column '{timestamp_col}' not found.")

    ranked = pl.col(col).rank(method="average").over(timestamp_col)
    # Normalize to [0, 1]: (rank - min) / (max - min)
    rank_min = pl.col(col).rank(method="average").min().over(timestamp_col)
    rank_max = pl.col(col).rank(method="average").max().over(timestamp_col)
    normalized = (
        pl.when(rank_max == rank_min)
        .then(0.5)
        .otherwise((ranked - rank_min) / (rank_max - rank_min))
    )
    return df.select(normalized.alias(f"{col}_cs_rank"))[f"{col}_cs_rank"]


def exponential_decay_ma(series: pl.Series, halflife: int) -> pl.Series:
    """Exponential moving average with half-life parameter.

    Half-life → alpha = 1 - exp(-ln(2) / halflife).
    Polars ``ewm_mean(half_life=halflife)`` does the conversion internally.

    Args:
        series: Input numeric series.
        halflife: Number of periods for 50% weight decay.

    Returns:
        EMA series of same length as input.

    Example::

        s = pl.Series([1.0, 2.0, 4.0, 8.0])
        ema = exponential_decay_ma(s, halflife=2)
    """
    name = series.name or "ema"
    return series.ewm_mean(half_life=halflife, adjust=False).alias(f"{name}_ema{halflife}")


def information_coefficient(
    predicted: pl.Series,
    realized: pl.Series,
) -> float:
    """Spearman rank correlation between predicted and realized returns.

    Industry standard metric for signal quality at WorldQuant / Two Sigma.
    IC > 0.05 is considered statistically meaningful.

    Args:
        predicted: Model signal or alpha scores.
        realized: Actual (forward) returns aligned with predicted.

    Returns:
        Spearman IC in [-1, 1]. Returns 0.0 if insufficient data.

    Example::

        ic = information_coefficient(
            pl.Series([0.1, 0.5, -0.2]),
            pl.Series([0.05, 0.4, -0.15]),
        )
        assert ic > 0.9
    """
    if predicted.len() < 2 or realized.len() < 2:
        return 0.0
    if predicted.len() != realized.len():
        raise ValueError("predicted and realized must have the same length.")

    # Spearman = Pearson correlation of ranks
    df_corr = pl.DataFrame({"p": predicted, "r": realized})
    ic = df_corr.select(
        pl.corr(pl.col("p").rank(), pl.col("r").rank(), method="pearson")
    ).to_series()[0]

    return float(ic) if ic is not None and not math.isnan(ic) else 0.0


def winsorize(
    series: pl.Series,
    lower: float = 0.01,
    upper: float = 0.99,
) -> pl.Series:
    """Clip outliers at lower/upper quantiles.

    Essential pre-processing before z-scoring to prevent outliers from
    dominating cross-sectional signal.

    Args:
        series: Input numeric series.
        lower: Lower quantile clip (default 0.01 = 1st percentile).
        upper: Upper quantile clip (default 0.99 = 99th percentile).

    Returns:
        Winsorized series of same length.

    Example::

        s = pl.Series([1.0, 2.0, 3.0, 100.0])
        ws = winsorize(s, lower=0.0, upper=0.9)
        assert ws[-1] <= 3.0
    """
    lo = series.quantile(lower, interpolation="linear")
    hi = series.quantile(upper, interpolation="linear")
    name = series.name or "winsorized"
    return series.clip(lo, hi).alias(name)


def cross_sectional_zscore(
    df: pl.DataFrame,
    col: str,
    timestamp_col: str = "timestamp",
) -> pl.Series:
    """Z-score ``col`` within each timestamp cross-section.

    Mean and std computed over all assets at each timestamp.

    Args:
        df: Long-format DataFrame with ``timestamp_col`` and ``col``.
        col: Column to normalize.
        timestamp_col: Column identifying the cross-sectional time slice.

    Returns:
        Z-scored series (inline group normalization via Polars .over()).

    Example::

        df = pl.DataFrame({"timestamp": ["t1"]*3, "signal": [1.0, 2.0, 3.0]})
        z = cross_sectional_zscore(df, "signal")
        # → [-1.0, 0.0, 1.0]
    """
    mean_expr = pl.col(col).mean().over(timestamp_col)
    std_expr = pl.col(col).std().over(timestamp_col)
    zscore_expr = pl.when(std_expr == 0.0).then(0.0).otherwise((pl.col(col) - mean_expr) / std_expr)
    return df.select(zscore_expr.alias(f"{col}_cs_zscore"))[f"{col}_cs_zscore"]


"""
# Pytest-style unit tests:

def test_rolling_zscore_mean_approx_zero() -> None:
    import polars as pl
    from qtrader.features.statistical.transforms import rolling_zscore

    s = pl.Series([float(i) for i in range(100)])
    z = rolling_zscore(s, window=20).drop_nulls()
    # Last rolling window should have mean ~ 0 and std ~ 1
    assert abs(float(z.mean())) < 0.1

def test_information_coefficient_perfect() -> None:
    import polars as pl
    from qtrader.features.statistical.transforms import information_coefficient

    signal = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    realized = pl.Series([0.1, 0.2, 0.3, 0.4, 0.5])
    ic = information_coefficient(signal, realized)
    assert abs(ic - 1.0) < 1e-9, f"Expected IC=1.0, got {ic}"

def test_winsorize_clips_outliers() -> None:
    import polars as pl
    from qtrader.features.statistical.transforms import winsorize

    s = pl.Series([1.0, 2.0, 3.0, 4.0, 1000.0])
    ws = winsorize(s, lower=0.0, upper=0.8)
    assert float(ws.max()) <= 4.0, "Outlier should be clipped"
"""
