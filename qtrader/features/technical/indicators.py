import polars as pl
from qtrader.features.base import Feature


class RSI(Feature):
    """Relative Strength Index."""

    def __init__(self, period: int = 14) -> None:
        self.period = period

    @property
    def name(self) -> str:
        return f"rsi_{self.period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        close = df["close"]
        delta = close.diff()
        gain = delta.clip(lower_bound=0)
        loss = -delta.clip(upper_bound=0)
        
        avg_gain = gain.rolling_mean(window_size=self.period)
        avg_loss = loss.rolling_mean(window_size=self.period)
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.alias(self.name)


class SMA(Feature):
    """Simple Moving Average."""

    def __init__(self, period: int) -> None:
        self.period = period

    @property
    def name(self) -> str:
        return f"sma_{self.period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return df["close"].rolling_mean(window_size=self.period).alias(self.name)


class BollingerBands(Feature):
    """Bollinger Bands."""

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.period = period
        self.num_std = num_std

    @property
    def name(self) -> str:
        return f"bb_{self.period}_{self.num_std}"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        sma = df["close"].rolling_mean(window_size=self.period)
        std = df["close"].rolling_std(window_size=self.period)
        
        upper = sma + (self.num_std * std)
        lower = sma - (self.num_std * std)
        
        return pl.DataFrame({
            f"{self.name}_upper": upper,
            f"{self.name}_lower": lower,
            f"{self.name}_middle": sma
        })
