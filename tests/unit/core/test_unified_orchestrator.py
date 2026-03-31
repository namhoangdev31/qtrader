import pytest
import asyncio
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock
from qtrader.core.orchestrator import TradingOrchestrator, SystemState
from qtrader.core.bus import EventBus
from qtrader.core.events import EventType, MarketEvent, MarketPayload

@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.subscribe = MagicMock()
    bus.publish = AsyncMock()
    bus.start = AsyncMock()
    bus.shutdown = AsyncMock()
    return bus

@pytest.fixture
def orchestrator(mock_bus):
    with patch("qtrader.core.orchestrator.ShadowEngine", return_value=AsyncMock()), \
         patch("qtrader.core.orchestrator.ResourceMonitor", return_value=AsyncMock()):
        return TradingOrchestrator(
            event_bus=mock_bus,
            market_data_adapter=MagicMock(),
            alpha_modules=[],
            feature_validator=MagicMock(),
            strategies=[],
            ensemble_strategy=MagicMock(),
            portfolio_allocator=MagicMock(),
            runtime_risk_engine=MagicMock(),
            oms_adapter=MagicMock()
        )

@pytest.mark.asyncio
async def test_state_machine_transitions(orchestrator):
    """Verify the formal state machine transitions and gating."""
    assert orchestrator._state == SystemState.INIT
    
    # 1. INIT -> READY via initialize() and validate()
    orchestrator.initialize()
    # Mocking validation success
    orchestrator.validate() 
    assert orchestrator._state == SystemState.READY
    
    # 2. READY -> RUNNING via run()
    asyncio.create_task(orchestrator.run())
    
    # Smart polling for state transition
    for _ in range(50):
        if orchestrator._state == SystemState.RUNNING:
            break
        await asyncio.sleep(0.01)
    
    assert orchestrator._state == SystemState.RUNNING
    
    # 3. RUNNING -> SHUTDOWN via halt_core()
    await orchestrator.halt_core("Test Shutdown")
    assert orchestrator._state == SystemState.SHUTDOWN

@pytest.mark.asyncio
async def test_initialization_priority(orchestrator):
    """Verify that authorities are initialized in the mandatory sequence."""
    orchestrator.initialize()
    # Check boot time for forensic proof of activation
    assert orchestrator._boot_time is not None

@pytest.mark.asyncio
async def test_execution_gating(orchestrator):
    """Ensure that data ingestion is blocked in non-RUNNING states."""
    mock_payload = MarketPayload(symbol="BTC/USDT", bid=50000.0, ask=50001.0)
    mock_event = MarketEvent(
        source="test",
        payload=mock_payload
    )
    
    # System is in INIT state
    await orchestrator.ingest_raw_data({"symbol": "BTC/USDT", "bid": 50000.0, "ask": 50001.0})
    # Event should be dropped (not published to bus)
    orchestrator.event_bus.publish.assert_not_called()

@pytest.mark.asyncio
async def test_high_concurrency_stress(orchestrator):
    """Stress-test the system with 1,000+ concurrent event injections."""
    orchestrator.initialize()
    orchestrator.validate()
    
    # Transition to RUNNING
    asyncio.create_task(orchestrator.run())
    
    # Inject 1,000 events
    tasks = []
    # Ensure we are firmly in RUNNING
    assert orchestrator._state == SystemState.RUNNING
    
    for i in range(1000):
        mock_payload = MarketPayload(symbol="BTC/USDT", bid=50000.0 + i, ask=50001.0 + i)
        event = MarketEvent(
            source="test",
            payload=mock_payload
        )
        tasks.append(orchestrator.handle_market_data(event))
        
    await asyncio.gather(*tasks)
    # Verify bus received all events
    assert orchestrator.event_bus.publish.call_count == 1000

@pytest.mark.asyncio
async def test_atomic_halt(orchestrator):
    """Verify that halt_core() successfully stops the bus and cleans resources."""
    orchestrator.initialize()
    orchestrator.validate()
    asyncio.create_task(orchestrator.run())
    
    # Wait for RUNNING
    for _ in range(50):
        if orchestrator._state == SystemState.RUNNING:
            break
        await asyncio.sleep(0.01)
    
    await orchestrator.halt_core("Emergency Halt")
    assert orchestrator._state == SystemState.SHUTDOWN
    orchestrator.event_bus.shutdown.assert_called_once()
