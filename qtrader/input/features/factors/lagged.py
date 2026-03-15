"""Lagged return and autocorrelation features.

All computations are pure Polars expression chains — no numpy, no Python loops.
"""

from __future__ import annotations

import polars as pl

from qtrader.input.features.base import BaseFeature

__all__ = ["LaggedReturn", "AutoCorrelation", "ReturnVolatility", "SkewFeature"]


class LaggedReturn(BaseFeature):
    """Log return lagged by N periods.

    Used to test if past returns predict future returns (momentum / reversal).

    Attributes:
        lag: Number of periods to lag (default 1).
        period: Return look-back length (default 1).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, lag: int = 1, period: int = 1) -> None:
        self.lag = lag
        self.period = period
        self.name = f"lagged_ret_l{lag}_p{period}"
        self.min_periods = lag + period + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute log(close_t / close_{t-period}) shifted by ``lag`` bars.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            Lagged return series; leading values are null.
        """
        self.validate_inputs(df)
        raw_ret = (pl.col("close") / pl.col("close").shift(self.period)).log(base=2.718281828)
        lagged = raw_ret.shift(self.lag)
        return df.select(lagged.alias(self.name))[self.name]


class AutoCorrelation(BaseFeature):
    """Rolling autocorrelation of returns at a given lag.

    Measures persistence (positive) or mean-reversion (negative) tendency.

    Attributes:
        window: Rolling window for autocorrelation (default 20).
        lag: Correlation lag (default 1).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, window: int = 20, lag: int = 1) -> None:
        self.window = window
        self.lag = lag
        self.name = f"autocorr_w{window}_l{lag}"
        self.min_periods = window + lag + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute rolling autocorrelation of 1-period returns.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            Rolling autocorrelation series; leading values are null.
        """
        self.validate_inputs(df)
        ret = pl.col("close").pct_change()
        # Polars rolling autocorrelation: corr between ret and ret.shift(lag) over window
        autocorr = ret.rolling_corr(ret.shift(self.lag), window_size=self.window)
        return df.select(autocorr.alias(self.name))[self.name]


class ReturnVolatility(BaseFeature):
    """Rolling realized volatility (annualized std of log returns).

    Attributes:
        window: Rolling window in periods (default 20).
        periods_per_year: Annualization factor (default 252).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, window: int = 20, periods_per_year: int = 252) -> None:
        self.window = window
        self.periods_per_year = periods_per_year
        self.name = f"realized_vol_{window}"
        self.min_periods = window

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute annualized rolling realized volatility.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            Annualized vol series; first ``window - 1`` values are null.
        """
        self.validate_inputs(df)
        log_ret = pl.col("close").log(base=2.718281828).diff()
        ann_vol = log_ret.rolling_std(self.window) * (self.periods_per_year ** 0.5)
        return df.select(ann_vol.alias(self.name))[self.name]


class SkewFeature(BaseFeature):
    """Rolling skewness of log returns.

    Positive skew means right-tailed (occasional large gains).
    Negative skew means left-tailed (crash risk).

    Attributes:
        window: Rolling window in periods (default 60).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, window: int = 60) -> None:
        self.window = window
        self.name = f"return_skew_{window}"
        self.min_periods = window

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute rolling skewness of log returns.

        Args:
            df: DataFrame with ``close`` column.

        Returns:
            Rolling skewness series; first ``window - 1`` values are null.
        """
        self.validate_inputs(df)
        log_ret = pl.col("close").log(base=2.718281828).diff()
        skew = log_ret.rolling_skew(self.window)
        return df.select(skew.alias(self.name))[self.name]


"""
# Pytest-style unit tests:

def test_lagged_return_matches_manual() -> None:
    import polars as pl
    import math
    from qtrader.input.features.factors.lagged import LaggedReturn

    prices = [100.0, 110.0, 121.0, 133.1, 146.41]
    df = pl.DataFrame({"close": prices})
    lr = LaggedReturn(lag=1, period=1)
    result = lr.compute(df)
    # row 3 (0-indexed): lag=1, period=1 → log(121/110) shifted by 1 = log(110/100) at t=3
    expected = math.log(110.0 / 100.0)
    assert abs(result[3] - expected) < 1e-9

def test_return_volatility_non_negative() -> None:
    import polars as pl
    from qtrader.input.features.factors.lagged import ReturnVolatility

    prices = [float(100 + i * 0.5 + (i % 4) * 0.2) for i in range(40)]
    df = pl.DataFrame({"close": prices})
    factor = ReturnVolatility(window=20)
    result = factor.compute(df).drop_nulls()
    assert (result >= 0.0).all(), "Volatility must be non-negative"
"""
