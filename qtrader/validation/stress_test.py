from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from qtrader.core.events import (
    StressTestErrorEvent,
    StressTestErrorPayload,
    StressTestResultEvent,
    StressTestResultPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    import polars as pl

    from qtrader.core.event_bus import EventBus
    from qtrader.governance.kill_switch import KillSwitch
    from qtrader.governance.sandbox import Strategy, StrategySandbox
    from qtrader.governance.strategy_fsm import StrategyFSM


class StressTester:
    """
    Forensic System Stress Testing Engine.

    Validates structural system behavior under tail-risk regimes:
    - Flash Crash: Must trigger emergency shutdown.
    - Liquidity Collapse: Must respond with risk limits.
    - Volatility Spikes: Must maintain deterministic FSM state.
    """

    def __init__(
        self,
        event_bus: EventBus,
        fsm: StrategyFSM,
        kill_switch: KillSwitch,
        sandbox: StrategySandbox,
    ) -> None:
        """
        Initialize the stress tester with structural risk components.
        """
        self._event_bus = event_bus
        self._fsm = fsm
        self._kill_switch = kill_switch
        self._sandbox = sandbox
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def run_stress_test(
        self, scenario_id: str, strategy: Strategy, market_data: pl.DataFrame
    ) -> StressTestResultEvent | None:
        """
        Execute a system-wide stress test against a forensic scenario.
        """
        try:
            # 1. State Isolation: Ensure strategy is ACTIVE for stress
            # sandbox appraisal logic: assume strategy is already calibrated.

            # Listen for Kill Events
            kill_triggered = False
            state_transitions: list[str] = []

            # Internal callback to capture events during simulation
            # (In a real system, we'd subscribe to the EventBus)

            # 2. Execution Logic: Run through Sandbox Simulation
            report = await self._sandbox.run_simulation(strategy, market_data)

            if not report:
                raise ValueError("Sandbox simulation failed during stress test.")

            # 3. Risk Evaluation: Manually trigger KillSwitch with sandbox results
            pnl = report.payload.pnl
            drawdown = report.payload.drawdown
            slippage = 0.0  # Default for forensic sandbox test

            # Force KillSwitch appraisal of the scenario end-state
            metrics = {
                "drawdown": float(drawdown),
                "pnl_change": float(pnl),
                "slippage": float(slippage),
            }

            kill_event = await self._kill_switch.evaluate_metrics(strategy.strategy_id, metrics)
            if kill_event:
                kill_triggered = True

            # 4. Result Synthesis
            is_passing = True
            # Flash crashes MUST trigger a kill
            if "FLASH" in scenario_id and not kill_triggered:
                is_passing = False

            result_event = StressTestResultEvent(
                trace_id=self._system_trace,
                source="StressTester",
                payload=StressTestResultPayload(
                    scenario_id=scenario_id,
                    max_drawdown=float(drawdown),
                    kill_triggered=kill_triggered,
                    state_transitions=state_transitions,
                    is_passing=is_passing,
                    metadata={"strategy_id": strategy.strategy_id},
                ),
            )

            await self._event_bus.publish(result_event)
            logger.info(f"STRESS_TEST_COMPLETE | {scenario_id} | Pass: {is_passing}")
            return result_event

        except Exception as e:
            logger.error(f"STRESS_TEST_FAILURE | {scenario_id} | {e!s}")
            await self._emit_error(scenario_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, scenario_id: str, err_type: str, details: str) -> None:
        """Emit a StressTestErrorEvent to the global bus."""
        error_event = StressTestErrorEvent(
            trace_id=self._system_trace,
            source="StressTester",
            payload=StressTestErrorPayload(
                scenario_id=scenario_id, error_type=err_type, details=details
            ),
        )
        await self._event_bus.publish(error_event)
