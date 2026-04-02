import time
from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import EventType
from qtrader.execution.state_builder import StateBuilder

# Test Constants
SYMBOL = "BTC_USDT"
VENUE = "binance"
STATE_DIM = 7


@pytest.mark.asyncio
async def test_state_builder_compute_success() -> None:
    """Verify state vector generation for industrial-grade execution optimization."""
    bus = AsyncMock()
    builder = StateBuilder(bus)

    # Market State S_t
    market_state = {
        "bid": 1000.0,
        "ask": 1000.2,
        "bid_size": 10.0,
        "ask_size": 20.0,
        "volatility": 0.01,
        "latency": 5.0,
    }

    state_vector = await builder.build(market_state, SYMBOL, VENUE)

    # Feature Verifications:
    # 1. Spread (Normalized) -> (0.2 / 1000.1) / 0.005 = 0.0399 / 0.005 approx 0.04
    # 2. Imbalance -> (10 - 20) / 30 = -0.333
    # 3. Microprice -> Relative to mid
    # 4. Volatility (Normalized) -> 0.01 / 0.05 = 0.2
    # 5. Queue Pos -> Default 0.5
    # 6. Fill Prob -> Heuristic
    # 7. Latency (Normalized) -> 5.0 / 100.0 = 0.05

    assert len(state_vector) == STATE_DIM
    assert state_vector[1] == pytest.approx(-0.3333333333)
    assert state_vector[3] == pytest.approx(0.2)
    assert state_vector[6] == pytest.approx(0.05)

    # Status Broadcast
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.EXECUTION_STATE_UPDATE


@pytest.mark.asyncio
async def test_state_builder_catastrophic_safety() -> None:
    """Verify failsafe behavior during missing market data."""
    builder = StateBuilder()

    # Empty Market state
    state_vector = await builder.build({}, SYMBOL, VENUE)

    # Failsafe should prevent crashes and return zero vector
    assert len(state_vector) == STATE_DIM
    assert all(v == 0.0 for v in state_vector)


@pytest.mark.asyncio
async def test_state_builder_failure_handling() -> None:
    """Verify industrial error recovery from malformed market states."""
    builder = StateBuilder()

    # Malformed state (None causing TypeError in math logic)
    state_vector = await builder.build(None, SYMBOL, VENUE)  # type: ignore

    assert len(state_vector) == STATE_DIM
    assert all(v == 0.0 for v in state_vector)


@pytest.mark.asyncio
async def test_state_builder_performance_latency() -> None:
    """Benchmark sub-1ms latency for industrial-grade feature engineering."""
    builder = StateBuilder()
    market_state = {
        "bid": 1000.0,
        "ask": 1000.2,
        "bid_size": 10.0,
        "ask_size": 20.0,
        "volatility": 0.01,
        "latency": 5.0,
    }

    start = time.perf_counter()
    for _ in range(1000):
        await builder.build(market_state, SYMBOL, VENUE)
    end = time.perf_counter()

    avg_latency_ms = (end - start) / 1000.0 * 1000.0
    # Strict industrial threshold: 1ms
    assert avg_latency_ms < 1.0
