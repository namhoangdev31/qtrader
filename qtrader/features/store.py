from pathlib import Path

import polars as pl

from qtrader.data.datalake import DataLake


class FeatureStore:
    """Offline Feature Store for persistent factor storage."""
    
    def __init__(self, base_path: str = "qtrader/data/feature_store") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.datalake = DataLake() # For reading raw data

    def _get_path(self, symbol: str, timeframe: str) -> Path:
        return self.base_path / f"symbol={symbol}" / f"tf={timeframe}" / "features.parquet"

    def save_features(self, df: pl.DataFrame, symbol: str, timeframe: str) -> None:
        """Persists features to the store."""
        path = self._get_path(symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(path, compression="snappy")

    def load_features(self, symbol: str, timeframe: str) -> pl.DataFrame:
        """Loads features from the store."""
        path = self._get_path(symbol, timeframe)
        if not path.exists():
            return pl.DataFrame()
        return pl.read_parquet(path)

    def get_feature_names(self, symbol: str, timeframe: str) -> list[str]:
        """Returns list of features available for a given symbol/timeframe."""
        df = self.load_features(symbol, timeframe)
        return df.columns if not df.is_empty() else []
