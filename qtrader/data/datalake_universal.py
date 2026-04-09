import logging
from pathlib import Path
from typing import Any
import polars as pl
from qtrader.core.config import Config


class UniversalDataLake:
    def __init__(
        self, base_uri: str | None = None, cloud_options: dict[str, Any] | None = None
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
        return f"{self.base_uri}/symbol={symbol}/tf={timeframe}/data.parquet"

    def save_data(self, df: pl.DataFrame, symbol: str, timeframe: str) -> None:
        target_uri = self._get_path(symbol, timeframe)
        if not target_uri.startswith(("s3://", "gs://", "az://")):
            Path(target_uri).parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(
            target_uri, compression="snappy", use_pyarrow=True, storage_options=self.cloud_options
        )
        logging.info(f"Saved {symbol} {timeframe} to {target_uri}")

    def load_data(self, symbol: str, timeframe: str) -> pl.DataFrame:
        uri = self._get_path(symbol, timeframe)
        return pl.read_parquet(uri, storage_options=self.cloud_options)

    def query_lake(self, sql: str) -> pl.DataFrame:
        pass
