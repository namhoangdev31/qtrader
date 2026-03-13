import asyncio

from qtrader.core.bus import EventBus
from qtrader.data.pipeline.base import DataPipeline


class BacktestEngine:
    """Event-driven backtesting engine."""

    def __init__(self, bus: EventBus, pipelines: list[DataPipeline]) -> None:
        self.bus = bus
        self.pipelines = pipelines
        self._running = False

    async def run(self) -> None:
        """Starts the backtest by running pipelines and processing events."""
        self._running = True
        
        # Start the event bus in the background
        bus_task = asyncio.create_task(self.bus.start())
        
        # Run all data pipelines (these will publish events to the bus)
        pipeline_tasks = [asyncio.create_task(p.run()) for p in self.pipelines]
        
        # Wait for all pipelines to finish reading data
        await asyncio.gather(*pipeline_tasks)
        
        # Once data is exhausted, wait a bit for bus to process remaining events
        await asyncio.sleep(1)
        
        await self.bus.shutdown()
        await bus_task
        self._running = False
        print("Backtest completed.")
