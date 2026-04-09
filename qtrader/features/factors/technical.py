from __future__ import annotations

import polars as pl

from qtrader.features.base import BaseFeature

__all__ = ["ATR", "MACD", "ROC", "RSI", "BollingerBands", "MomentumReturn"]


class RSI(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self.name = f"rsi_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        delta = pl.col("close").diff()
        gain = pl.when(delta > 0).then(delta).otherwise(0.0)
        loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
        alpha = 1.0 / self.period
        avg_gain = gain.ewm_mean(alpha=alpha, adjust=False)
        avg_loss = loss.ewm_mean(alpha=alpha, adjust=False)
        rsi_expr = (
            pl.when(avg_loss == 0.0)
            .then(100.0)
            .otherwise(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
        )
        result = df.with_columns([gain.alias("_gain"), loss.alias("_loss")]).select(
            [rsi_expr.alias(self.name)]
        )[self.name]
        return result


class ATR(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["high", "low", "close"]

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self.name = f"atr_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.Series:
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
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.name = f"macd_{fast}_{slow}_{signal}"
        self.min_periods = slow

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate_inputs(df)
        ema_fast = pl.col("close").ewm_mean(span=self.fast, adjust=False)
        ema_slow = pl.col("close").ewm_mean(span=self.slow, adjust=False)
        macd_line = ema_fast - ema_slow
        out = df.select([macd_line.alias("_macd_raw")])
        macd_signal = out["_macd_raw"].ewm_mean(span=self.signal, adjust=False)
        return pl.DataFrame(
            {
                "macd": out["_macd_raw"],
                "macd_signal": macd_signal,
                "macd_hist": out["_macd_raw"] - macd_signal,
            }
        )


class BollingerBands(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        self.period = period
        self.std_dev = std_dev
        self.name = f"bollinger_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate_inputs(df)
        mid = pl.col("close").rolling_mean(self.period)
        std = pl.col("close").rolling_std(self.period)
        upper = mid + self.std_dev * std
        lower = mid - self.std_dev * std
        out = df.select([mid.alias("bb_mid"), upper.alias("bb_upper"), lower.alias("bb_lower")])
        band_range = out["bb_upper"] - out["bb_lower"]
        pct_b = (
            pl.when(band_range == 0.0)
            .then(0.5)
            .otherwise((df["close"] - out["bb_lower"]) / band_range)
        )
        out = out.with_columns(pct_b.alias("bb_pct_b"))
        return out


class MomentumReturn(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self.name = f"momentum_{period}"
        self.min_periods = period + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        log_ret = (pl.col("close") / pl.col("close").shift(self.period)).log(base=2.718281828)
        return df.select(log_ret.alias(self.name))[self.name]


class ROC(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, period: int = 10) -> None:
        self.period = period
        self.name = f"roc_{period}"
        self.min_periods = period + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        roc = pl.col("close") / pl.col("close").shift(self.period) - 1.0
        return df.select(roc.alias(self.name))[self.name]
