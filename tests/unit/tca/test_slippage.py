import uuid
from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from qtrader.core.events import (
    DecisionTraceEvent,
    DecisionTracePayload,
    FillEvent,
    FillPayload,
)
from qtrader.tca.slippage import SlippageDecomposition

# Test Constants
DECISION_PRICE = 50000.0
MID_PRICE = 50020.0
FILL_PRICE = 50050.0
QUANTITY = 1.0


@pytest.mark.asyncio
async def test_slippage_decomposition_buy() -> None:
    """Verify that a BUY trade correctly decomposes slippage into timing and impact."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    
    # 1. Mock AuditStore
    store = MagicMock()
    store.query_olap.return_value = pl.DataFrame({
        "payload_json": ['{"payload": {"bids": [[50015, 1.0]], "asks": [[50025, 1.0]]}}']
    })
    
    # 2. Lifecycle Events
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
                quantity=QUANTITY, price=FILL_PRICE, commission=10.0
            )
        )
    ]
    
    engine = SlippageDecomposition(bus, store)
    result = await engine.decompose_trace(trace_id, events)
    
    assert result is not None # noqa: S101
    assert result.payload.timing_cost == pytest.approx(20.0) # noqa: S101
    assert result.payload.market_impact == pytest.approx(30.0) # noqa: S101


@pytest.mark.asyncio
async def test_slippage_decomposition_no_fills() -> None:
    """Verify that trades without execution events skip decomposition."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    store = MagicMock()
    
    events = [
        DecisionTraceEvent(
            trace_id=trace_id, source="Strat", timestamp=100,
            payload=DecisionTracePayload(
                model_id="M1", features={}, signal=0.8,
                decision_price=DECISION_PRICE, decision="BUY", config_version=1
            )
        )
    ]
    
    engine = SlippageDecomposition(bus, store)
    result = await engine.decompose_trace(trace_id, events)
    assert result is None # noqa: S101


@pytest.mark.asyncio
async def test_slippage_decomposition_mid_extraction_failure() -> None:
    """Verify handling of corrupt or invalid market data from analytical storage."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    store = MagicMock()
    # Invalid JSON string to trigger exception in _get_mid_price
    store.query_olap.return_value = pl.DataFrame({
        "payload_json": ["NOT_JSON"]
    })
    
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
            payload=FillPayload(order_id="O1", symbol="BTC", side="BUY", quantity=1.0, price=100.0)
        )
    ]
    
    engine = SlippageDecomposition(bus, store)
    result = await engine.decompose_trace(trace_id, events)
    assert result is None # noqa: S101
    assert bus.publish.called # noqa: S101


@pytest.mark.asyncio
async def test_slippage_decomposition_sell() -> None:
    """Verify side-multiplier logic for SELL trades."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    store = MagicMock()
    # Mid = 49980
    store.query_olap.return_value = pl.DataFrame({
        "payload_json": ['{"payload": {"bids": [[49975, 1.0]], "asks": [[49985, 1.0]]}}']
    })
    
    events = [
        DecisionTraceEvent(
            trace_id=trace_id, source="Strat", timestamp=100,
            payload=DecisionTracePayload(
                model_id="M1", features={}, signal=-0.8,
                decision_price=DECISION_PRICE, decision="SELL", config_version=1
            )
        ),
        FillEvent(
            trace_id=trace_id, source="Exch", timestamp=1000,
            payload=FillPayload(
                order_id="O1", symbol="BTC", side="SELL",
                quantity=QUANTITY, price=49950.0, commission=0.0
            )
        )
    ]
    
    engine = SlippageDecomposition(bus, store)
    result = await engine.decompose_trace(trace_id, events)
    assert result is not None # noqa: S101
    assert result.payload.timing_cost == pytest.approx(20.0) # noqa: S101
    assert result.payload.market_impact == pytest.approx(30.0) # noqa: S101
