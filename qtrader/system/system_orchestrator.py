from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Type
from uuid import UUID, uuid4

from qtrader.core.event_bus import EventBus
from qtrader.core.events import (
    BaseEvent, 
    EventType, 
    PipelineErrorEvent, 
    PipelineErrorPayload, 
    SystemEvent, 
    SystemPayload
)
from qtrader.core.state_store import StateStore
from qtrader.system.pipeline_validator import PipelineValidator

logger = logging.getLogger(__name__)


class SystemOrchestrator:
    """
    Principal Global System Orchestrator.
    
    The Orchestrator unifies all QTrader modules into a single, deterministic 
    event-driven pipeline. It handles module registration, architectural 
    certification, and authoritative event injection.
    
    Architecture:
    - **Wiring Enforcement**: Ensures all modules communicate via the EventBus.
    - **Trace Consistency**: Guarantees that the trace_id is preserved throughout the pipeline.
    - **Determinism**: Facilitates global state reconstruction by routing all 
      mutations through event-driven handlers.
    """

    def __init__(self, event_bus: EventBus, state_store: StateStore) -> None:
        """
        Initialize the orchestrator with core infrastructure.
        
        Args:
            event_bus: The central communication backbone.
            state_store: The authoritative system state holder.
        """
        self._event_bus = event_bus
        self._state_store = state_store
        self._modules: List[Any] = []
        self._validator = PipelineValidator()
        self._boot_time = asyncio.get_event_loop().time()

    def register_module(self, module: Any) -> None:
        """
        Register a top-level module in the pipeline.
        
        Each module is subjected to architectural review by the PipelineValidator 
        to ensure zero direct-coupling with other engines.
        
        Args:
            module: The module instance to integrate.
        """
        if self._validator.validate_module_architecture(module.__class__):
            self._modules.append(module)
            logger.info(f"ORCHESTRATOR_INTEGRATION | {module.__class__.__name__} connected.")
        else:
            logger.critical(f"ORCHESTRATOR_BOOT_FAILURE | Module {module.__class__.__name__} rejected.")
            raise RuntimeError(f"Module {module.__class__.__name__} failed architectural certification.")

    async def start(self) -> None:
        """
        Start the global pipeline and the event bus.
        """
        await self._event_bus.start()
        
        # Emit system readiness event
        boot_event = SystemEvent(
            trace_id=uuid4(),
            source="SystemOrchestrator",
            payload=SystemPayload(
                action="SYSTEM_READY",
                reason=f"Pipeline unified across {len(self._modules)} certified modules."
            )
        )
        await self._event_bus.publish(boot_event)
        logger.info("SYSTEM_ORCHESTRATOR | Global Deterministic Pipeline is now ACTIVE.")

    async def inject(self, event: BaseEvent) -> bool:
        """
        Authoritative entry point for market data or system commands.
        
        Ensures that every event entering the pipeline is compliant with 
        traceability and partition requirements.
        
        Args:
            event: The event to inject (e.g. MarketEvent).
            
        Returns:
            bool: True if accepted by the event bus.
        """
        # 1. Ensure Traceability (Audit Requirement)
        if not event.trace_id:
            # We must use model_copy since events are frozen
            event = event.model_copy(update={"trace_id": uuid4()})
            
        # 2. Publish to the bus for distributed routing
        return await self._event_bus.publish(event)

    async def stop(self) -> None:
        """Gracefully shutdown the global pipeline."""
        await self._event_bus.stop()
        logger.info("SYSTEM_ORCHESTRATOR | Global Pipeline HALTED.")

    def get_system_health(self) -> Dict[str, Any]:
        """Return metrics and health status of the integrated system."""
        bus_metrics = self._event_bus.get_metrics()
        return {
            "uptime_seconds": asyncio.get_event_loop().time() - self._boot_time,
            "module_count": len(self._modules),
            "event_throughput": bus_metrics.get("throughput", 0),
            "latency_ms": bus_metrics.get("avg_latency_ms", 0.0),
            "status": "OPERATIONAL" if self._event_bus._running else "STOPPED"
        }
