from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from qtrader.core.bus import EventBus
from qtrader.data.pipeline.base import DataPipeline

__all__ = ["BacktestEngine"]

log = logging.getLogger(__name__)


from qtrader.core.orchestrator import TradingOrchestrator, SystemState

@dataclass(slots=True)
class BacktestEngine:
    """Historical simulation engine controlled by the sovereign orchestrator.

    Args:
        orchestrator: The sovereign control layer for the simulation.
        pipelines: Collection of data pipelines feeding the simulation.
    """

    orchestrator: TradingOrchestrator
    pipelines: list[DataPipeline]
    name: str = "backtest"
    _running: bool = field(init=False, default=False)

    async def run(self) -> None:
        """Run simulation under sovereign control."""
        if self._running:
            return
        
        # 1. Mandatory Sovereign Sequence
        self.orchestrator.initialize()
        self.orchestrator.validate()
        
        # 2. Simulation Activation
        self._running = True
        log.info("BacktestEngine '%s' starting under sovereign control.", self.name)

        # Use the orchestrator's bus
        bus_task = asyncio.create_task(self.orchestrator.event_bus.start())
        pipeline_tasks = [asyncio.create_task(p.run()) for p in self.pipelines]

        try:
            await asyncio.gather(*pipeline_tasks)
        finally:
            # Clean halt via orchestrator
            await self.orchestrator.halt_core("Simulation_Complete")
            self._running = False
            log.info("BacktestEngine '%s' completed.", self.name)


    def run_until_complete(self) -> None:
        """Synchronous helper for running the engine in scripts/tests."""
        asyncio.run(self.run())


if __name__ == "__main__":
    # Minimal smoke test wiring (no real data pipelines).
    from qtrader.core.bus import EventBus as _Bus  # type: ignore[reimported]

    class _DummyPipeline(DataPipeline):  # type: ignore[misc]
        async def run(self) -> None:  # type: ignore[override]
            return None

    _bus = _Bus()
    _engine = BacktestEngine(bus=_bus, pipelines=[_DummyPipeline()])
    assert isinstance(_engine, BacktestEngine)

