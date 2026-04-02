import uuid
from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import (
    EventType,
    ImplementationShortfallEvent,
    ImplementationShortfallPayload,
    SlippageBreakdownEvent,
    SlippageBreakdownPayload,
)
from qtrader.tca.cost_attribution import CostAttribution

# Test Constants
TRACE_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_cost_attribution_full_trace() -> None:
    """Verify standard attribution of costs across impact, timing, and fees."""
    trace_id = TRACE_ID
    bus = AsyncMock()
    
    events = [
        ImplementationShortfallEvent(
            trace_id=trace_id, source="IS", timestamp=1000,
            payload=ImplementationShortfallPayload(
                trace_id=trace_id, decision_price=50.0, executed_price=50.05,
                quantity=1000.0, shortfall=50.0, total_cost=60.0, side="BUY"
            )
        ),
        SlippageBreakdownEvent(
            trace_id=trace_id, source="Slip", timestamp=1001,
            payload=SlippageBreakdownPayload(
                trace_id=trace_id, total_slippage=60.0,
                market_impact=30.0, timing_cost=20.0, fees=10.0
            )
        )
    ]
    
    engine = CostAttribution(bus)
    result = await engine.attribute_lifecycle_costs(trace_id, events)
    
    assert result is not None
    assert result.payload.total_cost == 60.0
    assert result.payload.impact_pct == pytest.approx(0.5) # 30/60
    assert result.payload.timing_pct == pytest.approx(1/3) # 20/60
    assert result.payload.fee_pct == pytest.approx(1/6) # 10/60


@pytest.mark.asyncio
async def test_cost_attribution_zero_cost() -> None:
    """Verify that zero-cost trades handle zero-division gracefully."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    events = [
        ImplementationShortfallEvent(
            trace_id=trace_id, source="IS", timestamp=100,
            payload=ImplementationShortfallPayload(
                trace_id=trace_id, decision_price=1.0, executed_price=1.0,
                quantity=1.0, shortfall=0.0, total_cost=0.0, side="BUY"
            )
        ),
        SlippageBreakdownEvent(
            trace_id=trace_id, source="S", timestamp=101,
            payload=SlippageBreakdownPayload(
                trace_id=trace_id, total_slippage=0.0,
                market_impact=0.0, timing_cost=0.0, fees=0.0
            )
        )
    ]
    
    engine = CostAttribution(bus)
    result = await engine.attribute_lifecycle_costs(trace_id, events)
    assert result is not None
    assert result.payload.total_cost == 0.0


@pytest.mark.asyncio
async def test_cost_attribution_missing_events() -> None:
    """Verify error emission for missing IS or Slippage diagnostic events."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    engine = CostAttribution(bus)
    
    # Case 1: Missing IS
    s_p = SlippageBreakdownPayload(
        trace_id=trace_id, total_slippage=1, market_impact=1, timing_cost=0, fees=0
    )
    s_event = SlippageBreakdownEvent(
        trace_id=trace_id, source="S", timestamp=1, payload=s_p
    )
    result = await engine.attribute_lifecycle_costs(trace_id, [s_event])
    assert result is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.ATTRIBUTION_ERROR

    # Case 2: Missing Slippage
    bus.reset_mock()
    is_p = ImplementationShortfallPayload(
        trace_id=trace_id, decision_price=1, executed_price=1, 
        quantity=1, shortfall=1, total_cost=1, side="B"
    )
    is_event = ImplementationShortfallEvent(
        trace_id=trace_id, source="I", timestamp=1, payload=is_p
    )
    result = await engine.attribute_lifecycle_costs(trace_id, [is_event])
    assert result is None
    assert bus.publish.call_args[0][0].event_type == EventType.ATTRIBUTION_ERROR


@pytest.mark.asyncio
async def test_cost_attribution_system_failure() -> None:
    """Verify industrial error handling during system-level exceptions."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    engine = CostAttribution(bus)
    
    # Trigger exception
    result = await engine.attribute_lifecycle_costs(trace_id, None) # type: ignore
    
    assert result is None
    assert bus.publish.called
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)
