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
from qtrader.tca.benchmark import ExecutionBenchmark

# Test Constants
DECISION_PRICE = 50000.0
EXEC_PRICE = 50050.0 
QUANTITY = 2.0


@pytest.mark.asyncio
async def test_execution_benchmark_buy() -> None:
    """Verify standard BUY comparison against market VWAP and TWAP."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    datalake = MagicMock()
    datalake.load_data.return_value = pl.DataFrame({
        "timestamp": [100, 500, 1000],
        "close": [50000.0, 50020.0, 50060.0],
        "volume": [10.0, 10.0, 0.0]
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
            payload=FillPayload(
                order_id="O1", symbol="BTC", side="BUY", 
                quantity=2.0, price=50050.0
            )
        )
    ]
    
    engine = ExecutionBenchmark(bus, datalake)
    result = await engine.benchmark_trade_lifecycle(trace_id, events)
    
    assert result is not None
    assert result.payload.vwap == 50010.0
    assert result.payload.twap == pytest.approx(50026.66666, rel=1e-5)


@pytest.mark.asyncio
async def test_execution_benchmark_zero_volume() -> None:
    """Verify fallback to close mean when total volume in window is zero."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    datalake = MagicMock()
    datalake.load_data.return_value = pl.DataFrame({
        "timestamp": [100, 500],
        "close": [50010.0, 50020.0],
        "volume": [0.0, 0.0]
    })
    
    events = [
        DecisionTraceEvent(
            trace_id=trace_id, source="Strat", timestamp=100,
            payload=DecisionTracePayload(
                model_id="M1", features={}, signal=0.8,
                decision_price=50000.0, decision="BUY", config_version=1
            )
        ),
        FillEvent(
            trace_id=trace_id, source="Exch", timestamp=500,
            payload=FillPayload(
                order_id="O1", symbol="BTC", side="BUY", 
                quantity=1.0, price=50030.0
            )
        )
    ]
    
    engine = ExecutionBenchmark(bus, datalake)
    result = await engine.benchmark_trade_lifecycle(trace_id, events)
    
    assert result is not None
    assert result.payload.vwap == 50015.0  # (50010+50020)/2


@pytest.mark.asyncio
async def test_execution_benchmark_empty_lake_or_window() -> None:
    """Verify fallback to arrival price when market data is empty level."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    datalake = MagicMock()
    engine = ExecutionBenchmark(bus, datalake)
    
    d_p = DecisionTracePayload(
        model_id="A", features={}, signal=1, 
        decision_price=DECISION_PRICE, decision="BUY", config_version=1
    )
    f_p = FillPayload(
        order_id="1", symbol="B", side="B", quantity=1.0, price=1.0
    )
    
    events = [
        DecisionTraceEvent(trace_id=trace_id, source="S", timestamp=100, payload=d_p),
        FillEvent(trace_id=trace_id, source="E", timestamp=100, payload=f_p)
    ]

    # Case 1: Empty market df
    datalake.load_data.return_value = pl.DataFrame()
    result = await engine.benchmark_trade_lifecycle(trace_id, events)
    assert result is not None and result.payload.vwap == DECISION_PRICE

    # Case 2: Window filter results in empty df
    datalake.load_data.return_value = pl.DataFrame({
        "timestamp": [1, 2], "close": [1, 2], "volume": [1, 2]
    })
    result = await engine.benchmark_trade_lifecycle(trace_id, events)
    assert result is not None and result.payload.vwap == DECISION_PRICE


@pytest.mark.asyncio
async def test_execution_benchmark_datalake_error() -> None:
    """Verify BenchmarkErrorEvent emission when DataLake retrieval fails."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    datalake = MagicMock()
    datalake.load_data.side_effect = RuntimeError("Disk Error")
    
    d_p = DecisionTracePayload(
        model_id="A", features={}, signal=1, 
        decision_price=DECISION_PRICE, decision="BUY", config_version=1
    )
    f_p = FillPayload(
        order_id="1", symbol="B", side="B", quantity=1.0, price=1.0
    )
    
    events = [
        DecisionTraceEvent(trace_id=trace_id, source="S", timestamp=100, payload=d_p),
        FillEvent(trace_id=trace_id, source="E", timestamp=100, payload=f_p)
    ]
    
    engine = ExecutionBenchmark(bus, datalake)
    result = await engine.benchmark_trade_lifecycle(trace_id, events)
    assert result is None
    assert bus.publish.called


@pytest.mark.asyncio
async def test_execution_benchmark_system_failure() -> None:
    """Verify error emission during critical system exceptions."""
    trace_id = uuid.uuid4()
    bus = AsyncMock()
    datalake = MagicMock()
    
    engine = ExecutionBenchmark(bus, datalake)
    result = await engine.benchmark_trade_lifecycle(trace_id, None) # type: ignore
    
    assert result is None
    assert bus.publish.called
