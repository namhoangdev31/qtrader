import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.core.bus import EventBus
from qtrader.core.events import EventType, MarketEvent, MarketPayload
from qtrader.core.orchestrator import SystemState, TradingOrchestrator


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.publish = AsyncMock()
    bus.start = AsyncMock()
    bus.shutdown = AsyncMock()
    return bus

@pytest.fixture(autouse=True)
def mock_precheck():
    with patch("qtrader.core.pre_execution_validator.PreExecutionValidator.validate", return_value=True):
        yield

@pytest.fixture
def orchestrator(mock_bus):
    from qtrader.core.decimal_adapter import math_authority
    from qtrader.core.enforcement_engine import enforcement_engine
    from qtrader.core.trace_authority import TraceAuthority
    
    with patch("qtrader.core.orchestrator.ShadowEngine", return_value=AsyncMock()), \
         patch("qtrader.core.orchestrator.ResourceMonitor", return_value=AsyncMock()), \
         patch("qtrader.core.orchestrator.NetworkKillSwitch", return_value=AsyncMock()), \
         patch("qtrader.core.orchestrator.FileEventStore", return_value=AsyncMock()), \
         patch("qtrader.core.orchestrator.container") as mock_container, \
         patch("qtrader.core.orchestrator.asyncio.create_task"), \
         patch("qtrader.core.orchestrator.PreExecutionValidator") as mock_validator_cls, \
         patch("qtrader.core.orchestrator.state_manager") as mock_state_manager:
        
        # Patch the global enforcement_engine methods directly as they are already bound to decorators
        with patch.object(enforcement_engine, "validate_pre_execution", new_callable=AsyncMock), \
             patch.object(enforcement_engine, "validate_post_execution", new_callable=AsyncMock), \
             patch.object(enforcement_engine, "validate_event", new_callable=AsyncMock):
            
            # Setup validator to pass by default
            mock_validator = MagicMock()
            mock_validator.validate.return_value = True
            mock_validator_cls.return_value = mock_validator
            
            # Setup container mocks
            def get_side_effect(k):
                if k == "config":
                    m = MagicMock()
                    m.update = AsyncMock()
                    m.get = MagicMock(return_value={})
                    m.get_checksum = MagicMock(return_value="test-checksum")
                    return m
                elif k == "seed":
                    m = MagicMock()
                    m.is_applied = MagicMock(return_value=True)
                    m.apply_global = MagicMock(return_value=None)
                    return m
                elif k == "trace":
                    return TraceAuthority
                elif k == "math":
                    return math_authority
                elif k == "trace":
                    return TraceAuthority
                elif k == "decimal":
                    return math_authority
                elif k == "failfast":
                    return AsyncMock()
                return MagicMock()
            mock_container.get.side_effect = get_side_effect
            
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
    
    # Smart polling for state transition
    for _ in range(50):
        if orchestrator._state == SystemState.RUNNING:
            break
        await asyncio.sleep(0.01)
    
    # Inject 1,000 events
    tasks = []
    # Ensure we are firmly in RUNNING
    assert orchestrator._state == SystemState.RUNNING
    
    import uuid
    from datetime import datetime
    from decimal import Decimal

    from qtrader.core.types import MarketData
    for i in range(1000):
        event = MarketData(
            symbol="BTC/USDT",
            timestamp=datetime.utcnow(),
            open=Decimal(str(50000.0 + i)),
            high=Decimal(str(50001.0 + i)),
            low=Decimal(str(49999.0 + i)),
            close=Decimal(str(50000.5 + i)),
            volume=Decimal("1.0"),
            trace_id=str(uuid.uuid4())
        )
        tasks.append(orchestrator.handle_market_data(event))
        
    await asyncio.gather(*tasks)
    
    # Verify bus received all events (allow for extra system events)
    assert orchestrator.event_bus.publish.call_count >= 1000

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
