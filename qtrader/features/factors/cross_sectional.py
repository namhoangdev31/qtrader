import polars as pl
from qtrader.features.base import Feature

class RelativeStrength(Feature):
    """Rank-based relative strength across assets."""
    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "rel_strength"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        # Note: Cross-sectional factors typically need whole universe.
        # This implementation expects a pre-calculated return or rank column.
        if "return" not in df.columns:
            return pl.Series(self.name, [0.0] * len(df))
        return df["return"].rank(descending=True).alias(self.name)
        # In a real system, the FactorEngine would handle multi-symbol DFs.
