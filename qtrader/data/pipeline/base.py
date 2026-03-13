from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from qtrader.core.event import MarketDataEvent


@runtime_checkable
class DataSource(Protocol):
    """Protocol for raw market data sources (e.g., WebSocket, REST)."""

    async def connect(self) -> None:
        ...

    async def stream(self) -> AsyncIterator[Any]:
        ...

    async def close(self) -> None:
        ...


@runtime_checkable
class DataNormalizer(Protocol):
    """Protocol for converting raw source data into MarketDataEvent."""

    def normalize(self, raw_data: Any) -> MarketDataEvent:
        ...


@runtime_checkable
class DataPipeline(Protocol):
    """Protocol for the overall data ingestion pipeline."""

    async def run(self) -> None:
        ...
