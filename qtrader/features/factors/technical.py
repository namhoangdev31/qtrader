"""Technical price-based factors.

All computations use pure Polars expression chains.
No numpy loops, no row-by-row Python iteration.
"""

from __future__ import annotations

import polars as pl

from qtrader.features.base import BaseFeature

__all__ = ["ATR", "MACD", "ROC", "RSI", "BollingerBands", "MomentumReturn"]


class RSI(BaseFeature):
    """Relative Strength Index (Wilder smoothing via EWM).

    Attributes:
        period: Lookback window (default 14).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self.name = f"rsi_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute RSI using Polars ewm_mean for Wilder smoothing.

        Args:
            df: DataFrame with ``close`` column, sorted ascending by time.

        Returns:
            RSI series in [0, 100]; first ``period - 1`` values are null.
        """
        self.validate_inputs(df)
        delta = pl.col("close").diff()
        gain = pl.when(delta > 0).then(delta).otherwise(0.0)
        loss = pl.when(delta < 0).then(-delta).otherwise(0.0)

        # Wilder smoothing ≡ EWM with alpha = 1/period
        alpha = 1.0 / self.period
        avg_gain = gain.ewm_mean(alpha=alpha, adjust=False)
        avg_loss = loss.ewm_mean(alpha=alpha, adjust=False)

        rsi_expr = pl.when(avg_loss == 0.0).then(100.0).otherwise(
            100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        )

        result = df.with_columns([
            gain.alias("_gain"),
            loss.alias("_loss"),
        ]).select([rsi_expr.alias(self.name)])[self.name]
        return result


class ATR(BaseFeature):
    """Average True Range.

    True range = max(H-L, |H-prev_C|, |L-prev_C|).
    Smoothed with EWM (Wilder).

    Attributes:
        period: Smoothing window (default 14).
    """

    version: str = "1.0"
    required_cols: list[str] = ["high", "low", "close"]

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self.name = f"atr_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute ATR via Polars expressions.

        Args:
            df: DataFrame with ``high``, ``low``, ``close`` columns.

        Returns:
            ATR series; first ``period - 1`` values are null.
        """
        self.validate_inputs(df)
        prev_close = pl.col("close").shift(1)
        hl = pl.col("high") - pl.col("low")
        hc = (pl.col("high") - prev_close).abs()
        lc = (pl.col("low") - prev_close).abs()

        tr = pl.max_horizontal(hl, hc, lc)
        alpha = 1.0 / self.period
        atr_expr = tr.ewm_mean(alpha=alpha, adjust=False)

        return df.select(atr_expr.alias(self.name))[self.name]


class MACD(BaseFeature):
    """Moving Average Convergence Divergence.

    Returns three columns: macd, macd_signal, macd_hist.

    Attributes:
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal EMA period (default 9).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.name = f"macd_{fast}_{slow}_{signal}"
        self.min_periods = slow

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute MACD, signal, and histogram.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            DataFrame with columns: ``macd``, ``macd_signal``, ``macd_hist``.
        """
        self.validate_inputs(df)
        ema_fast = pl.col("close").ewm_mean(span=self.fast, adjust=False)
        ema_slow = pl.col("close").ewm_mean(span=self.slow, adjust=False)
        macd_line = ema_fast - ema_slow

        out = df.select([
            macd_line.alias("_macd_raw"),
        ])
        macd_signal = out["_macd_raw"].ewm_mean(span=self.signal, adjust=False)

        return pl.DataFrame({
            "macd": out["_macd_raw"],
            "macd_signal": macd_signal,
            "macd_hist": out["_macd_raw"] - macd_signal,
        })


class BollingerBands(BaseFeature):
    """Bollinger Bands with %B position indicator.

    Attributes:
        period: Rolling window (default 20).
        std_dev: Number of standard deviations for bands (default 2.0).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        self.period = period
        self.std_dev = std_dev
        self.name = f"bollinger_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute Bollinger Bands and %B.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            DataFrame with columns: ``bb_upper``, ``bb_mid``, ``bb_lower``,
            ``bb_pct_b`` (position in band, 0=lower, 1=upper).
        """
        self.validate_inputs(df)
        mid = pl.col("close").rolling_mean(self.period)
        std = pl.col("close").rolling_std(self.period)
        upper = mid + self.std_dev * std
        lower = mid - self.std_dev * std

        out = df.select([
            mid.alias("bb_mid"),
            upper.alias("bb_upper"),
            lower.alias("bb_lower"),
        ])
        band_range = out["bb_upper"] - out["bb_lower"]
        pct_b = pl.when(band_range == 0.0).then(0.5).otherwise(
            (df["close"] - out["bb_lower"]) / band_range
        )
        out = out.with_columns(pct_b.alias("bb_pct_b"))
        return out


class MomentumReturn(BaseFeature):
    """Lookback momentum: log return over N periods.

    Attributes:
        period: Lookback period (default 20).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self.name = f"momentum_{period}"
        self.min_periods = period + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute N-period log return.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            Log momentum series; first ``period`` values are null.
        """
        self.validate_inputs(df)
        log_ret = (pl.col("close") / pl.col("close").shift(self.period)).log(base=2.718281828)
        return df.select(log_ret.alias(self.name))[self.name]


class ROC(BaseFeature):
    """Rate of Change (percentage).

    Attributes:
        period: Lookback period (default 10).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 10) -> None:
        self.period = period
        self.name = f"roc_{period}"
        self.min_periods = period + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute ROC = (close / close_N) - 1.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            ROC series in decimal form; first ``period`` values are null.
        """
        self.validate_inputs(df)
        roc = pl.col("close") / pl.col("close").shift(self.period) - 1.0
        return df.select(roc.alias(self.name))[self.name]


"""
# Pytest-style unit tests:

def test_rsi_output_range() -> None:
    import polars as pl
    from qtrader.features.factors.technical import RSI

    prices = [float(i) + (i % 3) * 0.5 for i in range(1, 40)]
    df = pl.DataFrame({"close": prices})
    rsi = RSI(period=14)
    result = rsi.compute(df)
    valid = result.drop_nulls()
    assert ((valid >= 0.0) & (valid <= 100.0)).all(), "RSI out of [0, 100] range"

def test_atr_non_negative() -> None:
    import polars as pl
    from qtrader.features.factors.technical import ATR

    df = pl.DataFrame({
        "high": [10.0, 11.0, 12.0, 11.5, 13.0] * 5,
        "low":  [9.0,  10.0, 11.0, 10.5, 12.0] * 5,
        "close":[9.5,  10.5, 11.5, 11.0, 12.5] * 5,
    })
    atr = ATR(period=5)
    result = atr.compute(df)
    assert (result.drop_nulls() > 0).all(), "ATR must be positive"

def test_macd_columns() -> None:
    import polars as pl
    from qtrader.features.factors.technical import MACD

    prices = [float(100 + i * 0.1 + (i % 5) * 0.3) for i in range(60)]
    df = pl.DataFrame({"close": prices})
    macd = MACD()
    result = macd.compute(df)
    assert {"macd", "macd_signal", "macd_hist"} <= set(result.columns)
"""
