import polars as pl

from qtrader.features.base import Feature


class OrderbookImbalance(Feature):
    """Measures relative depth between bid and ask."""
    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "obi"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        # Assuming df has 'bid_size' and 'ask_size' from L2 data
        if "bid_size" not in df.columns or "ask_size" not in df.columns:
            return pl.Series(self.name, [0.0] * len(df))
            
        bid = df["bid_size"]
        ask = df["ask_size"]
        return ((bid - ask) / (bid + ask)).alias(self.name)
