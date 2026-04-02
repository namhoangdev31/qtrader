import uuid
from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import (
    ImplementationShortfallEvent,
    ImplementationShortfallPayload,
    SlippageBreakdownEvent,
    SlippageBreakdownPayload,
)
from qtrader.tca.venue_ranking import VenueRankingEngine

# Test Constants
TRACE_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_venue_ranking_comparison() -> None:
    """Verify multiple venues are ranked correctly by weighted cost sum."""
    bus = AsyncMock()
    engine = VenueRankingEngine(bus, window_size=10)
    
    # 1. Dataset: Binance (High Cost) and Coinbase (Low Cost)
    events = [
        # BINANCE
        ImplementationShortfallEvent(
            trace_id=uuid.uuid4(), source="IS", timestamp=1,
            payload=ImplementationShortfallPayload(
                trace_id=uuid.uuid4(), decision_price=50.0, executed_price=50.1,
                quantity=10.0, shortfall=1.0, total_cost=1.2, side="BUY",
                metadata={"venue": "BINANCE"}
            )
        ),
        SlippageBreakdownEvent(
            trace_id=uuid.uuid4(), source="Slip", timestamp=2,
            payload=SlippageBreakdownPayload(
                trace_id=uuid.uuid4(), total_slippage=1.2,
                market_impact=0.4, timing_cost=0.5, fees=0.3,
                metadata={"venue": "BINANCE"}
            )
        ),
        # COINBASE
        ImplementationShortfallEvent(
            trace_id=uuid.uuid4(), source="IS", timestamp=3,
            payload=ImplementationShortfallPayload(
                trace_id=uuid.uuid4(), decision_price=50.0, executed_price=50.02,
                quantity=10.0, shortfall=0.2, total_cost=0.4, side="BUY",
                metadata={"venue": "COINBASE"}
            )
        ),
        SlippageBreakdownEvent(
            trace_id=uuid.uuid4(), source="Slip", timestamp=4,
            payload=SlippageBreakdownPayload(
                trace_id=uuid.uuid4(), total_slippage=0.4,
                market_impact=0.1, timing_cost=0.1, fees=0.2,
                metadata={"venue": "COINBASE"}
            )
        )
    ]
    
    results = await engine.process_tca_results(events)
    
    assert len(results) == 2
    assert results[0].payload.venue == "COINBASE"
    assert results[0].payload.rank == 1


@pytest.mark.asyncio
async def test_venue_ranking_rolling_window() -> None:
    """Verify that ranking engine respects window size and avoids stale data."""
    bus = AsyncMock()
    # If window=2, we have room for exactly 1 pair of (IS, SLIP)
    engine = VenueRankingEngine(bus, window_size=2)
    
    for i in range(3):
        events = [
            ImplementationShortfallEvent(
                trace_id=uuid.uuid4(), source="IS", timestamp=i,
                payload=ImplementationShortfallPayload(
                    trace_id=uuid.uuid4(), decision_price=float(i)*10.0,
                    executed_price=float(i)*10.0 + 1.0, quantity=1.0, 
                    shortfall=float(i)*10.0, total_cost=float(i)*10.0, side="B",
                    metadata={"venue": "V"}
                )
            ),
             SlippageBreakdownEvent(
                trace_id=uuid.uuid4(), source="Slip", timestamp=i,
                payload=SlippageBreakdownPayload(
                    trace_id=uuid.uuid4(), total_slippage=1.0, market_impact=0.5,
                    timing_cost=0.5, fees=0.0, metadata={"venue": "V"}
                )
            )
        ]
        results = await engine.process_tca_results(events)
    
    assert len(engine._history["V"]) == 2
    assert results[0].payload.metrics["avg_is"] == 20.0  # From i=2


@pytest.mark.asyncio
async def test_venue_ranking_edge_cases() -> None:
    """Verify robust handling of unknown venues and incomplete data batches."""
    bus = AsyncMock()
    engine = VenueRankingEngine(bus)
    
    # 1. Unknown Venue (Metadata Missing)
    ev_unknown = ImplementationShortfallEvent(
        trace_id=uuid.uuid4(), source="I", timestamp=1,
        payload=ImplementationShortfallPayload(
            trace_id=uuid.uuid4(), decision_price=1, executed_price=1,
            quantity=1, shortfall=1, total_cost=1, side="B"
            # No venue in metadata
        )
    )
    results = await engine.process_tca_results([ev_unknown])
    assert results == []
    
    # 2. Incomplete Batch (IS only, no SLIP for venue)
    ev_is = ImplementationShortfallEvent(
        trace_id=uuid.uuid4(), source="I", timestamp=2,
        payload=ImplementationShortfallPayload(
            trace_id=uuid.uuid4(), decision_price=1, executed_price=1,
            quantity=1, shortfall=1, total_cost=1, side="B",
            metadata={"venue": "X"}
        )
    )
    results = await engine.process_tca_results([ev_is])
    assert results == []
    
    # 3. System Error (None events)
    results = await engine.process_tca_results(None) # type: ignore
    assert results == []
