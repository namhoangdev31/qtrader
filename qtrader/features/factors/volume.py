import polars as pl

from qtrader.features.base import Feature


class VolumeZScore(Feature):
    """Z-score of volume relative to moving average."""
    def __init__(self, period: int = 20) -> None:
        self.period = period

    @property
    def name(self) -> str:
        return f"vol_zscore_{self.period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        vol = df["volume"]
        avg_vol = vol.rolling_mean(window_size=self.period)
        std_vol = vol.rolling_std(window_size=self.period)
        return ((vol - avg_vol) / std_vol).alias(self.name)
