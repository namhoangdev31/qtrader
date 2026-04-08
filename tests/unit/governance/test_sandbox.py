from typing import Any
from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from qtrader.core.events import EventType
from qtrader.governance.sandbox import StrategySandbox

# Test Constants
STRATEGY_ID = "SANDBOX_MOMENTUM_v1"
OHLC_DATA = pl.DataFrame(
    {
        "timestamp": [1, 2, 3, 4],
        "open": [100.0, 101.0, 102.0, 103.0],
        "high": [101.0, 102.0, 103.0, 104.0],
        "low": [99.0, 100.0, 101.0, 102.0],
        "close": [101.0, 102.0, 103.0, 104.0],
        "volume": [1000, 1100, 1200, 1300],
        "symbol": ["BTC"] * 4,
    }
)


class MockStrategy:
    """Industrial-grade mock strategy for sandbox appraisal testing."""

    def __init__(self, strategy_id: str) -> None:
        self.strategy_id = strategy_id
        self._signal: dict[str, Any] = {}
        self._call_count = 0

    def on_candle(self, df_candle: pl.DataFrame) -> None:
        # Simple signal logic: BUY on candle 1, SELL on candle 3
        self._call_count += 1
        if self._call_count == 1:
            self._signal = {"action": "BUY", "quantity": 1.0}
        elif self._call_count == 3:
            self._signal = {"action": "SELL", "quantity": 1.0}
        else:
            self._signal = {}

    def get_signal(self) -> dict[str, Any]:
        return self._signal


@pytest.mark.asyncio
async def test_sandbox_successful_simulation() -> None:
    """Verify that a strategy can run to completion and produce a performance report."""
    bus = AsyncMock()
    sandbox = StrategySandbox(bus)
    strategy = MockStrategy(STRATEGY_ID)

    report = await sandbox.run_simulation(strategy, OHLC_DATA)

    # 1. Verification of the Report
    assert report is not None
    assert report.payload.strategy_id == STRATEGY_ID

    # Trade 1: Close 101.0 (BUY 1.0)
    # Trade 2: Close 103.0 (SELL 1.0)
    # Net PnL = (SELL 103) - (BUY 101) = 2.0
    assert report.payload.pnl == pytest.approx(2.0)
    assert report.payload.trade_count == 2
    assert report.payload.status == "SUCCESS"

    # 2. Verification of Event Bus Publish
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.SANDBOX_REPORT


@pytest.mark.asyncio
async def test_sandbox_empty_simulation() -> None:
    """Verify metrics for strategy that generates zero signals."""
    bus = AsyncMock()
    sandbox = StrategySandbox(bus)

    # Mock strategy with NO signals
    strategy = MagicMock(strategy_id=STRATEGY_ID)
    strategy.get_signal.return_value = {}

    report = await sandbox.run_simulation(strategy, OHLC_DATA)

    assert report is not None
    assert report.payload.pnl == 0.0
    assert report.payload.trade_count == 0
    assert report.payload.status == "EMPTY"


@pytest.mark.asyncio
async def test_sandbox_system_failure() -> None:
    """Verify industrial error handling during sandbox-level exceptions."""
    bus = AsyncMock()
    sandbox = StrategySandbox(bus)

    # Malformed market data causing exception
    report = await sandbox.run_simulation(None, None)  # type: ignore

    assert report is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.SANDBOX_ERROR
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)
