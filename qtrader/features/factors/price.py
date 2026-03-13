import polars as pl

from qtrader.features.base import Feature


class PriceMomentum(Feature):
    """Simple price momentum."""
    def __init__(self, period: int = 20) -> None:
        self.period = period
    
    @property
    def name(self) -> str:
        return f"mom_{self.period}"
    
    def compute(self, df: pl.DataFrame) -> pl.Series:
        return (df["close"] / df["close"].shift(self.period) - 1).alias(self.name)

class RollingVolatility(Feature):
    """Rolling standard deviation of returns."""
    def __init__(self, period: int = 20) -> None:
        self.period = period

    @property
    def name(self) -> str:
        return f"vol_{self.period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        returns = df["close"].pct_change()
        return returns.rolling_std(window_size=self.period).alias(self.name)
