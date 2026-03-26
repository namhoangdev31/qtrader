from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

from qtrader.core.events import (
    KillErrorEvent,
    KillErrorPayload,
    StrategyKillEvent,
    StrategyKillPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.governance.strategy_fsm import StrategyFSM


class KillSwitch:
    """
    Real-Time Emergency Shutdown System for Algorithmic Strategies.

    Provides the absolute failsafe layer to instantly disable strategies:
    - Drawdown > Threshold
    - PnL Crash Detection
    - Anomalous Slippage Detection
    """

    def __init__(
        self,
        event_bus: EventBus,
        fsm: StrategyFSM,
        max_drawdown: float = 0.1,  # 10%
        pnl_crash_threshold: float = -5000.0,  # USD
        slippage_limit: float = 0.02,  # 2%
    ) -> None:
        """
        Initialize the kill switch with structural risk limits.
        """
        self._event_bus = event_bus
        self._fsm = fsm
        self._max_drawdown = max_drawdown
        self._pnl_crash_threshold = pnl_crash_threshold
        self._slippage_limit = slippage_limit
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def evaluate_metrics(
        self, strategy_id: str, metrics: dict[str, float]
    ) -> StrategyKillEvent | None:
        """
        Evaluate live metrics and trigger an emergency kill if thresholds are breached.
        """
        try:
            if metrics is None:
                raise ValueError("Metrics vector is NULL")

            drawdown = metrics.get("drawdown", 0.0)
            pnl_change = metrics.get("pnl_change", 0.0)
            slippage = metrics.get("slippage", 0.0)

            kill_triggered = False
            reason = "NORMAL_OPERATION"
            breached_metric = "NONE"
            threshold = 0.0

            # 1. Kill Conditions: Kill = OR(all violations)
            if drawdown > self._max_drawdown:
                kill_triggered = True
                reason = "MAX_DRAWDOWN_BREACHED"
                breached_metric = "drawdown"
                threshold = self._max_drawdown
            elif pnl_change < self._pnl_crash_threshold:
                kill_triggered = True
                reason = "PNL_CRASH_DETECTED"
                breached_metric = "pnl_change"
                threshold = self._pnl_crash_threshold
            elif slippage > self._slippage_limit:
                kill_triggered = True
                reason = "ANOMALOUS_SLIPPAGE_DETECTED"
                breached_metric = "slippage"
                threshold = self._slippage_limit

            if not kill_triggered:
                return None

            # 2. Sequential Force Shutdown: Transition FSM to KILLED
            fsm_success = await self._fsm.transition(
                strategy_id, "KILLED", reason=f"KILL_SWITCH_TRIGGERED: {reason}"
            )

            # 3. Kill Broadcast
            kill_event = StrategyKillEvent(
                trace_id=self._system_trace,
                source="KillSwitch",
                payload=StrategyKillPayload(
                    strategy_id=strategy_id,
                    reason=reason,
                    metric=breached_metric,
                    threshold=threshold,
                    metadata={
                        "fsm_transition_success": fsm_success,
                        "timestamp_ms": int(time.time() * 1000),
                    },
                ),
            )

            await self._event_bus.publish(kill_event)
            logger.critical(f"STRATEGY_KILLED | {strategy_id} | {reason}")

            return kill_event

        except Exception as e:
            logger.error(f"KILL_SWITCH_FAILURE | {strategy_id} | {e!s}")
            await self._emit_error(strategy_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, strategy_id: str, err_type: str, details: str) -> None:
        """Emit a KillErrorEvent to the global bus."""
        error_event = KillErrorEvent(
            trace_id=self._system_trace,
            source="KillSwitch",
            payload=KillErrorPayload(
                strategy_id=strategy_id, error_type=err_type, details=details
            ),
        )
        await self._event_bus.publish(error_event)
