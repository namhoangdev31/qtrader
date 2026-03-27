from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.events import EventType
from qtrader.execution.cost_model import CostModel

# Test Constants
STRATEGY_ID = "TCA_STRAT_01"
EXPECTED_FAIL_COST = 1e18


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with cost model parameters."""
    cfg = MagicMock()
    cfg.cost_model = {
        "impact_k": 0.15,
        "timing_alpha": 0.05,
        "fixed_fee": 1.0,
        "prop_fee": 0.0002,
    }
    return cfg


@pytest.mark.asyncio
async def test_cost_model_compute_success(execution_config: MagicMock) -> None:
    """Verify cost model decomposition for industrial-grade TCA (Implementation Shortfall)."""
    bus = AsyncMock()
    model = CostModel(execution_config, bus)

    # Market State S_t
    state = {
        "symbol": "BTC_USDT",
        "liquidity": 1000.0,
        "volatility": 0.01,
        "spread": 0.2,  # absolute spread
        "price": 100.0,
    }

    # Execution Action a_t
    action = {"order_size": 100.0, "delay": 1.0, "venue": "binance"}

    report = await model.compute(state, action, STRATEGY_ID)

    # 1. Validation of Impact (k * (100/1000)^2 = 0.15 * 0.01 = 0.0015)
    # 2. Validation of Timing (alpha * 0.01 * 1 = 0.0005)
    # 3. Validation of Spread (0.2 / 2 * 100 = 10.0)
    # 4. Validation of Fees (1.0 + 0.0002 * 100 * 100 = 1.0 + 2.0 = 3.0)
    # Total => 0.0015 + 0.0005 + 10.0 + 3.0 = 13.002

    assert report["total_cost"] == pytest.approx(13.002)  # noqa: S101
    assert report["impact_cost"] == pytest.approx(0.0015)  # noqa: S101
    assert report["timing_cost"] == pytest.approx(0.0005)  # noqa: S101
    assert report["spread_cost"] == pytest.approx(10.0)  # noqa: S101
    assert report["fee_cost"] == pytest.approx(3.0)  # noqa: S101

    # Status Broadcast
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.EXECUTION_COST_REPORT  # noqa: S101


@pytest.mark.asyncio
async def test_cost_model_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify failsafe behavior during missing liquidity or market data."""
    model = CostModel(execution_config)

    # Empty Market state
    report = await model.compute({"liquidity": 0.0}, {"order_size": 100.0})

    # Failsafe should prevent crashes and use default liquidity (1.0)
    # Impact = 0.15 * (100 / 1.0)^2 = 1500.0
    assert report["impact_cost"] == 1500.0  # noqa: S101, PLR2004


@pytest.mark.asyncio
async def test_cost_model_failure_handling(execution_config: MagicMock) -> None:
    """Verify industrial error recovery from malformed execution states."""
    model = CostModel(execution_config)

    # Malformed state (None causing TypeError in math logic)
    report = await model.compute(None, {"order_size": 100.0})  # type: ignore

    # Should return large finite cost on failure
    assert report["total_cost"] == EXPECTED_FAIL_COST  # noqa: S101
    assert report["impact_cost"] == 0.0  # noqa: S101
