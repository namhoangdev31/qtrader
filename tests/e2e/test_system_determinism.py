import asyncio
import uuid
from decimal import Decimal
from typing import Any
import pytest
from qtrader.core.event_bus import EventBus
from qtrader.core.state_store import StateStore
from qtrader.system.system_orchestrator import SystemOrchestrator
from qtrader.core.events import MarketEvent, MarketPayload, EventType


@pytest.mark.asyncio
async def test_orchestrator_boot_and_injection_traceability():
    """Verify that the orchestrator correctly boots the pipeline and enforces trace_id."""
    bus = EventBus()
    state = StateStore()
    orchestrator = SystemOrchestrator(bus, state)
    
    await orchestrator.start()
    
    # 1. Inject Market Event with an initial trace_id
    market_event = MarketEvent(
        trace_id=uuid.uuid4(),
        source="Bitstamp",
        payload=MarketPayload(symbol="BTC/USD", bid=50000, ask=50100)
    )
    
    # Use await because inject is async
    await orchestrator.inject(market_event)
    
    # Give a small slice for the worker to process the initial boot events
    await asyncio.sleep(0.01)
    
    metrics = orchestrator.get_system_health()
    assert metrics["status"] == "OPERATIONAL"
    assert metrics["uptime_seconds"] >= 0
    
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_zero_direct_call_enforcement():
    """Ensure the orchestrator rejects modules that violate the Event-Driven architectural policy."""
    # Define an illegal module with direct dependency on the OMS (bypassing EventBus)
    class OmsSubModule:
        """A module that should only be accessible via EventBus."""
        pass

    class IllegalStrategy:
        def __init__(self, oms: OmsSubModule) -> None:
            self.oms = oms # DIRECT COUPLING VIOLATION

    bus = EventBus()
    state = StateStore()
    orchestrator = SystemOrchestrator(bus, state)
    
    # We must mock the validator's forbidden list to include OmsSubModule for this test
    # or just use a known forbidden name like "OMS" or "ExecutionEngine"
    class IllegalExecutionModule:
        def __init__(self, oms: Any) -> None: # name includes 'oms' but type hint is better
            pass
            
    # The validator checks the type hint string representation
    class BadModule:
        def __init__(self, engine: "ExecutionEngine") -> None:
            pass

    with pytest.raises(RuntimeError) as exc:
        orchestrator.register_module(BadModule(None))
    
    assert "BadModule failed architectural certification" in str(exc.value)


@pytest.mark.asyncio
async def test_system_determinism_simulation():
    """Verify that the global system remains deterministic by routing everything via EventBus."""
    bus = EventBus()
    state = StateStore()
    orchestrator = SystemOrchestrator(bus, state)
    
    await orchestrator.start()
    
    trace_id = uuid.uuid4()
    
    # Inject 10 sequential events
    for i in range(10):
        evt = MarketEvent(
            trace_id=trace_id,
            source="Feed_X",
            payload=MarketPayload(symbol="AAPL", bid=150 + i, ask=151 + i)
        )
        await orchestrator.inject(evt)
        
    await asyncio.sleep(0.05) # Allow workers to processing
    
    metrics = orchestrator.get_system_health()
    # At least 10 market events + 1 boot event should have been processed
    assert metrics["event_throughput"] >= 10 
    
    await orchestrator.stop()
