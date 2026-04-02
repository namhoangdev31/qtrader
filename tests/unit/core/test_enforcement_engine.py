from unittest.mock import AsyncMock, MagicMock, patch

from qtrader.core.enforcement_engine import EnforcementEngine, guard
from qtrader.core.events import BaseEvent
from qtrader.core.exceptions import ConstraintViolation
from qtrader.core.violation_handler import violation_handler


@pytest.fixture
def mock_container():
    with patch("qtrader.core.enforcement_engine.container") as m:
        m.get.side_effect = lambda name: MagicMock()
        yield m

@pytest.fixture
def engine(mock_container):
    return EnforcementEngine()

@pytest.mark.asyncio
async def test_validate_pre_execution_success(engine):
    """Verify pre-execution validation passes with trace_id."""
    context = {"trace_id": "test-trace"}
    await engine.validate_pre_execution(context)
    assert engine.checks_performed == 1
    assert engine.violations_detected == 0

@pytest.mark.asyncio
async def test_validate_pre_execution_violation(engine):
    """Verify pre-execution validation fails without trace_id."""
    context = {}  # Empty context, no trace_id
    violation_handler.failfast.handle_error = AsyncMock()
    
    await engine.validate_pre_execution(context)
    
    assert engine.violations_detected == 1
    violation_handler.failfast.handle_error.assert_called_once()

@pytest.mark.asyncio
async def test_validate_event_success(engine):
    """Verify event validation passes for a compliant event."""
    event = MagicMock(spec=BaseEvent)
    event.trace_id = "test-trace"
    # No financial fields that are floats
    
    await engine.validate_event(event)
    assert engine.checks_performed == 1
    assert engine.violations_detected == 0

@pytest.mark.asyncio
async def test_validate_event_numeric_violation(engine):
    """Verify C4 Numeric violation when float is detected in financial fields."""
    event = MagicMock(spec=BaseEvent)
    event.trace_id = "test-trace"
    event.price = 50000.0  # Float! Should be Decimal or int
    
    # Mocking failfast to avoid system halt during test
    violation_handler.failfast.handle_error = AsyncMock()
    
    await engine.validate_event(event)
    assert engine.violations_detected == 1
    violation_handler.failfast.handle_error.assert_called_once()

@pytest.mark.asyncio
async def test_guard_decorator_success(engine):
    """Verify @guard decorator works for successful execution."""
    
    @guard(engine)
    async def sample_func(trace_id="test"):
        return "success"
    
    result = await sample_func(trace_id="test")
    assert result == "success"
    assert engine.checks_performed >= 1

@pytest.mark.asyncio
async def test_guard_decorator_violation(engine):
    """Verify @guard decorator catches violations before execution."""
    
    @guard(engine)
    async def sample_func():
        return "success"
    
    violation_handler.failfast.handle_error = AsyncMock()
    
    # Missing trace_id in call
    await sample_func()
    
    assert engine.violations_detected == 1
    violation_handler.failfast.handle_error.assert_called_once()
