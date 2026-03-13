from typing import Any, Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class DataStore(Protocol):
    """Protocol for storing and retrieving time-series market data."""

    async def write(self, symbol: str, df: pl.DataFrame) -> None:
        ...

    async def read(self, symbol: str, start_time: Any = None, end_time: Any = None) -> pl.DataFrame:
        ...

    async def list_symbols(self) -> list[str]:
        ...
