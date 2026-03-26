import uuid
from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import (
    DecisionTraceEvent,
    DecisionTracePayload,
    FillEvent,
    FillPayload,
)
from qtrader.tca.implementation_shortfall import ImplementationShortfall

# Test Constants
DECISION_PRICE = 50000.0
FILL_PRICE = 50050.0
QUANTITY = 2.0
COMMISSION = 10.0


@pytest.mark.asyncio
async def test_implementation_shortfall_buy() -> None:
    """Verify correct IS calculation for a BUY order with positive slippage."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    events = [
        DecisionTraceEvent(
            trace_id=trace_id, source="Strat", timestamp=100,
            payload=DecisionTracePayload(
                model_id="M1", features={}, signal=0.8,
                decision_price=DECISION_PRICE, decision="BUY", config_version=1
            )
        ),
        FillEvent(
            trace_id=trace_id, source="Exch", timestamp=1000,
            payload=FillPayload(
                order_id="O1", symbol="BTC", side="BUY",
                quantity=QUANTITY, price=FILL_PRICE, commission=COMMISSION
            )
        )
    ]
    
    tca = ImplementationShortfall(bus)
    result = await tca.compute_and_emit(trace_id, events)
    
    assert result is not None # noqa: S101
    assert result.payload.shortfall == pytest.approx(100.0) # noqa: S101
    assert result.payload.total_cost == pytest.approx(110.0) # noqa: S101


@pytest.mark.asyncio
async def test_implementation_shortfall_hold() -> None:
    """Verify that HOLD decisions result in zero shortfall if fills occur (anomaly check)."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    events = [
        DecisionTraceEvent(
            trace_id=trace_id, source="Strat", timestamp=100,
            payload=DecisionTracePayload(
                model_id="M1", features={}, signal=0.0,
                decision_price=DECISION_PRICE, decision="HOLD", config_version=1
            )
        ),
        FillEvent(
            trace_id=trace_id, source="Exch", timestamp=1000,
            payload=FillPayload(
                order_id="O1", symbol="BTC", side="BUY",
                quantity=1.0, price=50000.0, commission=0.0
            )
        )
    ]
    
    tca = ImplementationShortfall(bus)
    result = await tca.compute_and_emit(trace_id, events)
    
    assert result is not None # noqa: S101
    assert result.payload.shortfall == 0.0 # noqa: S101


@pytest.mark.asyncio
async def test_implementation_shortfall_no_fills() -> None:
    """Verify that an incomplete trade lifecycle (no fills) is handled gracefully."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    events = [
        DecisionTraceEvent(
            trace_id=trace_id, source="Strat", timestamp=100,
            payload=DecisionTracePayload(
                model_id="M1", features={}, signal=0.8,
                decision_price=DECISION_PRICE, decision="BUY", config_version=1
            )
        )
    ]
    
    tca = ImplementationShortfall(bus)
    result = await tca.compute_and_emit(trace_id, events)
    
    assert result is None # noqa: S101
    assert not bus.publish.called # noqa: S101


@pytest.mark.asyncio
async def test_implementation_shortfall_critical_error() -> None:
    """Verify that system exceptions in compute are caught and emitted via TCAErrorEvent."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    # Passing None to compute_and_emit to trigger an exception in the loop
    tca = ImplementationShortfall(bus)
    result = await tca.compute_and_emit(trace_id, None) # type: ignore
    
    assert result is None # noqa: S101
    assert bus.publish.called # noqa: S101
    event = bus.publish.call_args[0][0]
    assert event.payload.error_type == "SYSTEM_FAILURE" # noqa: S101


@pytest.mark.asyncio
async def test_implementation_shortfall_missing_decision() -> None:
    """Verify failure recovery when the benchmark event is missing from the stream."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    events = [
        FillEvent(
            trace_id=trace_id, source="Exch", timestamp=1,
            payload=FillPayload(order_id="O1", symbol="BTC", side="BUY", quantity=1.0, price=100.0)
        )
    ]
    
    tca = ImplementationShortfall(bus)
    result = await tca.compute_and_emit(trace_id, events)
    
    assert result is None # noqa: S101
    assert bus.publish.called # noqa: S101
    assert bus.publish.call_args[0][0].payload.error_type == "MISSING_DECISION" # noqa: S101
