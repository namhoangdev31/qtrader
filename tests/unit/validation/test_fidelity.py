from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from qtrader.core.events import EventType
from qtrader.validation.fidelity import FidelityEngine

# Test Constants
STRATEGY_ID = "BTC_QUANT_V1"


@pytest.mark.asyncio
async def test_fidelity_engine_compute_success() -> None:
    """Verify fidelity computation with aligned trade vectors."""
    bus = AsyncMock()
    engine = FidelityEngine(bus)

    # Generate Aligned Datasets
    # Backtest trades
    bt = pl.DataFrame(
        {
            "timestamp": [100, 200, 300],
            "symbol": ["BTC"] * 3,
            "price": [1000.0, 1010.0, 1020.0],
            "pnl": [10.0, 10.0, 10.0],
            "slippage": [0.001, 0.001, 0.001],
        }
    )

    # 2. Live trades with 0.1% drift in PnL/Price
    live = pl.DataFrame(
        {
            "timestamp": [101, 201, 301],
            "symbol": ["BTC"] * 3,
            "price": [1001.0, 1011.0, 1021.0],
            "pnl": [9.0, 9.0, 9.0],
            "slippage": [0.002, 0.002, 0.002],
        }
    )

    event = await engine.compute_fidelity(STRATEGY_ID, bt, live)

    # 1. Validation of Fidelity Score
    # error = 1.0 per trade, bt_pnl = 10.0. score approx 0.9.
    assert event is not None  # noqa: S101
    assert event.payload.fidelity_score == pytest.approx(0.9)  # noqa: S101
    assert event.payload.pnl_diff == pytest.approx(1.0)  # noqa: S101
    assert event.payload.price_diff == pytest.approx(1.0)  # noqa: S101

    # 2. Validation of Event Bus Publish
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.FIDELITY_REPORT  # noqa: S101


@pytest.mark.asyncio
async def test_fidelity_engine_zero_trade_failure() -> None:
    """Verify that an empty trade dataset triggers a system failure."""
    bus = AsyncMock()
    engine = FidelityEngine(bus)

    bt = pl.DataFrame({"timestamp": [], "symbol": [], "price": [], "pnl": [], "slippage": []})
    live = MagicMock()  # Should trigger exception or return empty

    event = await engine.compute_fidelity(STRATEGY_ID, bt, live)  # type: ignore

    assert event is None  # noqa: S101
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.FIDELITY_ERROR  # noqa: S101
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)  # noqa: S101
