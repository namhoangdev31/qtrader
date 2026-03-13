import logging
from pathlib import Path

import polars as pl


class DataLake:
    """Manages raw market data stored as Parquet files."""
    
    def __init__(self, base_path: str = "qtrader/data/datalake") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, symbol: str, timeframe: str) -> Path:
        return self.base_path / f"symbol={symbol}" / f"tf={timeframe}" / "data.parquet"

    def save_data(self, df: pl.DataFrame, symbol: str, timeframe: str) -> None:
        """Saves a Polars DataFrame to the partitioned datalake."""
        target_path = self._get_path(symbol, timeframe)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use Snappy compression for good balance of speed and size
        df.write_parquet(target_path, compression="snappy")
        logging.info(f"Saved {symbol} {timeframe} to {target_path}")

    def load_data(self, symbol: str, timeframe: str) -> pl.DataFrame:
        """Loads data from the datalake."""
        path = self._get_path(symbol, timeframe)
        if not path.exists():
            raise FileNotFoundError(f"No data found for {symbol} at {timeframe}")
        return pl.read_parquet(path)

    def get_all_symbols(self) -> list[str]:
        return [p.name.split("=")[1] for p in self.base_path.glob("symbol=*")]
