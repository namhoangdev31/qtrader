"""Volume and microstructure factors.

All computations use pure Polars expression chains — no numpy, no Python loops.
"""

from __future__ import annotations

import polars as pl

from qtrader.features.base import BaseFeature

__all__ = ["OBV", "VWAP", "DollarVolume", "ForceIndex", "VolumeRatio"]


class OBV(BaseFeature):
    """On-Balance Volume.

    Cumulates volume with sign of price change.
    Rising OBV confirms uptrend; falling OBV signals distribution.
    """

    name: str = "obv"
    version: str = "1.0"
    required_cols: list[str] = ["close", "volume"]
    min_periods: int = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute OBV as cumulative signed volume.

        Args:
            df: DataFrame with ``close`` and ``volume`` columns.

        Returns:
            OBV series aligned with df rows.
        """
        self.validate_inputs(df)
        direction = (
            pl.when(pl.col("close") > pl.col("close").shift(1))
            .then(1.0)
            .when(pl.col("close") < pl.col("close").shift(1))
            .then(-1.0)
            .otherwise(0.0)
        )

        signed_vol = (direction * pl.col("volume")).fill_null(0.0)
        return df.select(signed_vol.cum_sum().alias(self.name))[self.name]


class VWAP(BaseFeature):
    """Session VWAP (cumulative, resets each day).

    typical_price = (high + low + close) / 3
    vwap = cumsum(typical_price * volume) / cumsum(volume)

    Note: For daily or multi-day bars, this approximates VWAP over the full
    period. For intraday use, ensure df is pre-filtered to one session.
    """

    name: str = "vwap"
    version: str = "1.0"
    required_cols: list[str] = ["high", "low", "close", "volume"]
    min_periods: int = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute VWAP as cumulative typical-price-volume ratio.

        Args:
            df: DataFrame with ``high``, ``low``, ``close``, ``volume``.

        Returns:
            VWAP series aligned with df.
        """
        self.validate_inputs(df)
        tp = (pl.col("high") + pl.col("low") + pl.col("close")) / 3.0
        tpv = tp * pl.col("volume")
        cum_tpv = tpv.cum_sum()
        cum_vol = pl.col("volume").cum_sum()
        vwap_expr = pl.when(cum_vol == 0.0).then(None).otherwise(cum_tpv / cum_vol)
        return df.select(vwap_expr.alias(self.name))[self.name]


class DollarVolume(BaseFeature):
    """Dollar volume = close × volume.

    Commonly used as a liquidity proxy. High dollar volume → easy execution.
    Rolling sum provides N-day liquidity indicator.

    Attributes:
        rolling_window: Optional rolling sum window (None = raw bar value).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close", "volume"]
    min_periods: int = 1

    def __init__(self, rolling_window: int | None = None) -> None:
        self.rolling_window = rolling_window
        self.name = (
            "dollar_volume" if rolling_window is None else f"dollar_volume_{rolling_window}d"
        )

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute dollar volume, optionally with rolling sum.

        Args:
            df: DataFrame with ``close`` and ``volume`` columns.

        Returns:
            Dollar volume series.
        """
        self.validate_inputs(df)
        dv = pl.col("close") * pl.col("volume")
        if self.rolling_window is not None:
            dv = dv.rolling_sum(self.rolling_window)
        return df.select(dv.alias(self.name))[self.name]


class VolumeRatio(BaseFeature):
    """Volume / rolling average volume ratio.

    Value > 1 indicates above-average volume (potential breakout/breakdown).

    Attributes:
        period: Rolling window for average volume (default 20).
    """

    version: str = "1.0"
    required_cols: list[str] = ["volume"]

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self.name = f"volume_ratio_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute volume / rolling_mean(volume, period).

        Args:
            df: DataFrame with ``volume`` column.

        Returns:
            Volume ratio series; first ``period - 1`` values are null.
        """
        self.validate_inputs(df)
        avg_vol = pl.col("volume").rolling_mean(self.period)
        ratio = pl.when(avg_vol == 0.0).then(None).otherwise(pl.col("volume") / avg_vol)
        return df.select(ratio.alias(self.name))[self.name]


class ForceIndex(BaseFeature):
    """Elder's Force Index = price_change × volume.

    Positive values signal buying pressure; negative = selling pressure.
    Often smoothed with EMA.

    Attributes:
        ema_period: EMA smoothing (None = raw per-bar value).
    """

    version: str = "1.0"
    required_cols: list[str] = ["close", "volume"]

    def __init__(self, ema_period: int | None = 13) -> None:
        self.ema_period = ema_period
        self.name = "force_index" if ema_period is None else f"force_index_{ema_period}"
        self.min_periods = 1 if ema_period is None else ema_period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute Force Index, optionally EMA-smoothed.

        Args:
            df: DataFrame with ``close`` and ``volume`` columns.

        Returns:
            Force Index series.
        """
        self.validate_inputs(df)
        fi = pl.col("close").diff() * pl.col("volume")
        if self.ema_period is not None:
            fi = fi.ewm_mean(span=self.ema_period, adjust=False)
        return df.select(fi.fill_null(0.0).alias(self.name))[self.name]


"""
# Pytest-style unit tests:

def test_obv_increases_on_up_days() -> None:
    import polars as pl
    from qtrader.features.factors.volume import OBV

    df = pl.DataFrame({"close": [10.0, 11.0, 12.0], "volume": [100.0, 200.0, 150.0]})
    obv = OBV()
    result = obv.compute(df)
    assert result[-1] > result[0], "OBV should increase on consecutive up days"

def test_vwap_between_low_and_high() -> None:
    import polars as pl
    from qtrader.features.factors.volume import VWAP

    df = pl.DataFrame({
        "high": [12.0, 13.0, 14.0],
        "low":  [10.0, 11.0, 12.0],
        "close":[11.0, 12.0, 13.0],
        "volume":[100.0, 200.0, 150.0],
    })
    vwap = VWAP()
    result = vwap.compute(df).drop_nulls()
    lows = df["low"].to_list()
    highs = df["high"].to_list()
    for i, v in enumerate(result.to_list()):
        assert lows[i] <= v <= highs[i], f"VWAP {v} outside [low, high] at row {i}"

def test_dollar_volume_equals_close_times_volume() -> None:
    import polars as pl
    from qtrader.features.factors.volume import DollarVolume

    df = pl.DataFrame({"close": [100.0, 200.0], "volume": [10.0, 20.0]})
    dv = DollarVolume()
    result = dv.compute(df)
    assert result.to_list() == [1000.0, 4000.0]
"""
