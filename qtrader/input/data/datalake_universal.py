import logging
from pathlib import Path
from typing import Any

import polars as pl

from qtrader.core.config import Config


class UniversalDataLake:
    """
    Cloud-ready Data Lake abstraction.
    Supports local paths and S3/GCS URIs via Polars native integration.
    """
    
    def __init__(
        self,
        base_uri: str | None = None,
        cloud_options: dict[str, Any] | None = None,
    ) -> None:
        self.base_uri = base_uri or Config.DATALAKE_URI
        self.cloud_options = cloud_options or {
            "key": Config.S3_ACCESS_KEY,
            "secret": Config.S3_SECRET_KEY,
            "endpoint_url": Config.S3_ENDPOINT,
        }

        if not self.base_uri.startswith(("s3://", "gs://", "az://")):
            Path(self.base_uri).mkdir(parents=True, exist_ok=True)

    def _get_path(self, symbol: str, timeframe: str) -> str:
        # Use partitioning compatible with Hive/DuckDB
        return f"{self.base_uri}/symbol={symbol}/tf={timeframe}/data.parquet"

    def save_data(self, df: pl.DataFrame, symbol: str, timeframe: str) -> None:
        """Saves data to the Data Lake (Local or Cloud)."""
        target_uri = self._get_path(symbol, timeframe)
        
        # Polars write_parquet handles cloud URIs if fsspec/s3fs is installed
        # or natively in some versions.
        df.write_parquet(
            target_uri,
            compression="snappy",
            use_pyarrow=True,  # Recommended for cloud URIs
            storage_options=self.cloud_options,
        )
        logging.info(f"Saved {symbol} {timeframe} to {target_uri}")

    def load_data(self, symbol: str, timeframe: str) -> pl.DataFrame:
        """Loads data from the Data Lake."""
        uri = self._get_path(symbol, timeframe)
        return pl.read_parquet(uri, storage_options=self.cloud_options)

    def query_lake(self, sql: str) -> pl.DataFrame:
        """Query the lake directly if using DuckDB or Polars SQL."""
        # This would integrate with DuckDBClient to scan cloud Parquet
        pass
