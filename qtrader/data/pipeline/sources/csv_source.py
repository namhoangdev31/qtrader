import asyncio
from collections.abc import AsyncIterator
from typing import Any

import polars as pl

from qtrader.data.pipeline.base import DataSource


class CSVDataSource(DataSource):
    """Simple CSV data source for historical data ingestion."""

    def __init__(self, file_path: str, symbol: str) -> None:
        self.file_path = file_path
        self.symbol = symbol
        self._df: pl.DataFrame | None = None

    async def connect(self) -> None:
        # Load the CSV into memory (simplified for now)
        self._df = pl.read_csv(self.file_path)

    async def stream(self) -> AsyncIterator[Any]:
        if self._df is None:
            raise RuntimeError("DataSource not connected. Call connect() first.")

        # Stream row by row (simulating tick/bar events)
        for row in self._df.to_dicts():
            yield row
            await asyncio.sleep(0)  # Yield control

    async def close(self) -> None:
        self._df = None
