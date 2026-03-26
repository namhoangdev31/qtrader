from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

from qtrader.core.events import (
    ApprovalErrorEvent,
    ApprovalErrorPayload,
    StrategyApprovalEvent,
    StrategyApprovalPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import ModelRiskScoreEvent, SandboxReportEvent
    from qtrader.governance.strategy_fsm import StrategyFSM


class StrategyApprovalPipeline:
    """
    Institutional Strategy Approval Pipeline.

    Enforces structural governance rules before strategy deployment:
    - PnL > Threshold
    - Max Drawdown < Limit
    - Risk Score < Maximum Allowed Risk
    """

    def __init__(
        self,
        event_bus: EventBus,
        fsm: StrategyFSM,
        min_pnl: float = 0.0,
        max_dd: float = 0.2,  # 20% Drawdown
        max_risk: float = 0.5,
    ) -> None:
        """
        Initialize the pipeline with governance thresholds and FSM hook.
        """
        self._event_bus = event_bus
        self._fsm = fsm
        self._min_pnl = min_pnl
        self._max_dd = max_dd
        self._max_risk = max_risk
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def evaluate_strategy(
        self, sandbox_report: SandboxReportEvent, risk_event: ModelRiskScoreEvent
    ) -> StrategyApprovalEvent | None:
        """
        Perform the formal institutional appraisal of a strategy.

        Evaluates sandbox performance and quantitative risk scores to
        decide on formal approval and FSM transition.
        """
        strategy_id = "UNKNOWN"
        try:
            if not sandbox_report or not risk_event:
                raise ValueError("Sandbox Report or Risk Event is NULL")

            strategy_id = sandbox_report.payload.strategy_id
            pnl = sandbox_report.payload.pnl
            dd = sandbox_report.payload.drawdown
            risk_score = risk_event.payload.risk_score

            # 1. Approval Logic: A = 1 iff all constraints satisfied
            approved = True
            reason = "ALL_GATES_PASSED"

            if pnl < self._min_pnl:
                approved = False
                reason = f"INSUFFICIENT_PNL: {pnl:.4f} < {self._min_pnl}"
            elif dd > self._max_dd:
                approved = False
                reason = f"EXCESSIVE_DRAWDOWN: {dd:.4f} > {self._max_dd}"
            elif risk_score > self._max_risk:
                approved = False
                reason = f"EXCESSIVE_RISK: {risk_score:.4f} > {self._max_risk}"

            # 2. State Transition: Move to APPROVED in FSM if gates passed
            if approved:
                fsm_success = await self._fsm.transition(
                    strategy_id, "APPROVED", reason="PIPELINE_APPROVAL_GRANTED"
                )
                if not fsm_success:
                    approved = False
                    reason = "FSM_TRANSITION_FAILURE"

            # 3. Decision Broadcast
            event = StrategyApprovalEvent(
                trace_id=self._system_trace,
                source="StrategyApprovalPipeline",
                payload=StrategyApprovalPayload(
                    strategy_id=strategy_id,
                    approved=approved,
                    risk_score=risk_score,
                    reason=reason,
                    metadata={"timestamp_ms": int(time.time() * 1000)},
                ),
            )

            await self._event_bus.publish(event)
            status = "APPROVED" if approved else "REJECTED"
            logger.info(f"STRATEGY_APPROVAL_DECISION | {strategy_id} | {status} | {reason}")

            return event

        except Exception as e:
            logger.error(f"APPROVAL_PIPELINE_FAILURE | {strategy_id} | {e!s}")
            await self._emit_error(strategy_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, strategy_id: str, err_type: str, details: str) -> None:
        """Emit an ApprovalErrorEvent to the global bus."""
        error_event = ApprovalErrorEvent(
            trace_id=self._system_trace,
            source="StrategyApprovalPipeline",
            payload=ApprovalErrorPayload(
                strategy_id=strategy_id, error_type=err_type, details=details
            ),
        )
        await self._event_bus.publish(error_event)
