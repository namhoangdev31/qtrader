from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.events import EventType
from qtrader.validation.scenario_generator import ScenarioGenerator
from qtrader.validation.stress_test import StressTester


@pytest.mark.asyncio
async def test_scenario_generator_flash_crash() -> None:
    """Verify flash crash price vector generation."""
    sg = ScenarioGenerator()
    df = sg.generate_flash_crash("BTC", 1000.0, length=100, crash_depth=0.20)

    assert df.height == 100
    assert df["close"].min() <= 800.0
    assert df["symbol"][0] == "BTC"


@pytest.mark.asyncio
async def test_scenario_generator_vol_spike() -> None:
    """Verify volatility spike regime generation."""
    sg = ScenarioGenerator()
    df = sg.generate_volatility_spike("BTC", 1000.0, length=50, spike_start=10)

    assert df.height == 50
    assert df["symbol"][0] == "BTC"


@pytest.mark.asyncio
async def test_stress_test_flash_crash_trigger_kill() -> None:
    """Verify that a flash crash correctly triggers a kill switch event."""
    bus = AsyncMock()
    fsm = AsyncMock()
    kill_switch = AsyncMock()
    sandbox = AsyncMock()

    # Mock Sandbox Report showing high drawdown
    report = MagicMock()
    report.payload.strategy_id = "ALGO_STRAT"
    report.payload.pnl = -500.0
    report.payload.drawdown = 0.25
    sandbox.run_simulation.return_value = report

    # Mock Kill Event output
    kill_switch.evaluate_metrics.return_value = MagicMock()

    tester = StressTester(bus, fsm, kill_switch, sandbox)
    strategy = MagicMock()
    strategy.strategy_id = "ALGO_STRAT"

    # Generate scenario
    sg = ScenarioGenerator()
    data = sg.generate_flash_crash("BTC", 1000.0)

    result = await tester.run_stress_test("FLASH_CRASH_V1", strategy, data)

    # 1. Validation of Stress Test pass
    assert result is not None
    assert result.payload.kill_triggered
    assert result.payload.is_passing

    # 2. Validation of Event Bus Publish
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.STRESS_TEST_RESULT


@pytest.mark.asyncio
async def test_stress_test_failure_handling() -> None:
    """Verify industrial error handling during stress testing exceptions."""
    bus = AsyncMock()
    fsm = AsyncMock()
    kill_switch = AsyncMock()
    sandbox = AsyncMock()

    tester = StressTester(bus, fsm, kill_switch, sandbox)

    # Trigger Catastrophic Failure: Sandbox returns None
    sandbox.run_simulation.return_value = None

    result = await tester.run_stress_test("FLASH_ERROR", MagicMock(), None)  # type: ignore

    assert result is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.STRESS_TEST_ERROR
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)
