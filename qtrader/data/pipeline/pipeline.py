from qtrader.core.bus import EventBus
from qtrader.data.pipeline.base import DataNormalizer, DataPipeline, DataSource


class SimpleDataPipeline(DataPipeline):
    """Orchestrates ingestion from a single source to the event bus."""

    def __init__(
        self, 
        source: DataSource, 
        normalizer: DataNormalizer, 
        bus: EventBus
    ) -> None:
        self.source = source
        self.normalizer = normalizer
        self.bus = bus

    async def run(self) -> None:
        """Connects to source and publishes normalized events to the bus."""
        await self.source.connect()
        try:
            async for raw_data in self.source.stream():
                event = self.normalizer.normalize(raw_data)
                await self.bus.publish(event)
        finally:
            await self.source.close()
