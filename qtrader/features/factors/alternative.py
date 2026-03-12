import polars as pl
from qtrader.features.base import Feature

class SentimentFactor(Feature):
    """Placeholder for sentiment analysis factor."""
    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "sentiment"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        # Assuming df has 'sentiment_score' from external ingestion
        if "sentiment_score" not in df.columns:
            return pl.Series(self.name, [0.0] * len(df))
        return df["sentiment_score"].alias(self.name)
