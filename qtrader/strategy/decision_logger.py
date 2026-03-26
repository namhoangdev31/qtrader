from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qtrader.core.events import (
    DecisionErrorEvent,
    DecisionErrorPayload,
    DecisionTraceEvent,
    DecisionTracePayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from uuid import UUID

    from qtrader.core.config_manager import ConfigManager
    from qtrader.core.event_bus import EventBus


class DecisionLogger:
    """
    Principal Decision Trace and Logging Engine.
    
    Ensures that every trading decision is explainable and reproducible by 
    capturing the full context (features, model version, signal) before 
    order execution.
    """

    def __init__(self, event_bus: EventBus, config_manager: ConfigManager) -> None:
        """
        Initialize the decision logger with system hooks.
        """
        self._event_bus = event_bus
        self._config_manager = config_manager
        self._decisions_total = 0
        self._decisions_logged = 0

    async def log_decision(
        self,
        trace_id: UUID,
        model_id: str,
        features: dict[str, float],
        signal: float,
        decision_price: float,
        decision: str,
    ) -> bool:
        """
        Capture and verify a decision trace.
        
        Returns:
            bool: True if decision is logged and safe to execute. 
                  False if trace failed or features are missing.
        """
        self._decisions_total += 1

        # 1. Validation: No missing data allowed
        if not features:
            logger.error(f"DECISION_REJECTED | trace_id: {trace_id} | Features missing.")
            await self._emit_error(trace_id, "MISSING_FEATURES", "Feature vector was empty.")
            return False

        try:
            # 2. Snapshot system context
            config_version = self._config_manager.get_current_version()

            # 3. Construct and Publish Trace
            event = DecisionTraceEvent(
                trace_id=trace_id,
                source="DecisionLogger",
                payload=DecisionTracePayload(
                    model_id=model_id,
                    features=features,
                    signal=signal,
                    decision_price=decision_price,
                    decision=decision,
                    config_version=config_version,
                ),
            )

            # 4. Synchronous execution safety gate (Log must succeed)
            success = await self._event_bus.publish(event)
            if success:
                self._decisions_logged += 1
                logger.info(f"DECISION_TRACED | trace_id: {trace_id} | Model: {model_id}")
            else:
                logger.warning(f"DECISION_TRACE_DROP | trace_id: {trace_id}")
                
            return success

        except Exception as e:
            logger.critical(f"DECISION_TRACE_FAILURE | trace_id: {trace_id} | {e!s}")
            await self._emit_error(trace_id, "SYSTEM_FAILURE", str(e))
            return False

    async def _emit_error(self, trace_id: UUID, err_type: str, details: str) -> None:
        """Helper to emit DecisionErrorEvent for audit and alerting."""
        error_event = DecisionErrorEvent(
            trace_id=trace_id,
            source="DecisionLogger",
            payload=DecisionErrorPayload(
                module_name="DecisionLogger",
                error_type=err_type,
                details=details,
            ),
        )
        await self._event_bus.publish(error_event)

    def get_metrics(self) -> dict[str, Any]:
        """
        Retrieve observability metrics for the decision trace system.
        """
        total = self._decisions_total
        logged = self._decisions_logged
        rate = (logged / total) if total > 0 else 1.0
        return {
            "decision_logged_rate": float(rate),
            "total_decisions": total,
            "coverage_100": rate == 1.0
        }
