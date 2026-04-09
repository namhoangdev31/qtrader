from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable
from qtrader.core.events import MarketEvent


@runtime_checkable
class DataSource(Protocol):
    async def connect(self) -> None: ...

    async def stream(self) -> AsyncIterator[Any]: ...

    async def close(self) -> None: ...
        pass


@runtime_checkable
class DataNormalizer(Protocol):
    def normalize(self, raw_data: Any) -> MarketEvent: ...
        pass


@runtime_checkable
class DataPipeline(Protocol):
    async def run(self) -> None: ...
        pass
