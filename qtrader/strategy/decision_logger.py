from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from qtrader.core.event_bus import EventBus
from qtrader.core.events import (
    DecisionErrorEvent, 
    DecisionErrorPayload, 
    DecisionTraceEvent, 
    DecisionTracePayload
)
from qtrader.core.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class DecisionLogger:
    """
    Authoritative Decision Trace and Logging Engine.
    
    Responsible for capturing the binary-perfect context of every trade decision, 
    including feature vectors, model identifiers, and strategy configurations. 
    This ensures that every trade intention is fully explainable and 
    reproducible during system audits.
    
    Architecture:
    - **A-Priori Logging**: Records intent BEFORE the risk engine or execution gate.
    - **Traceability**: Enforces strict trace_id linkage across the strategy pipeline.
    - **Context Capture**: Snapshot-based logging of configuration versions.
    """

    def __init__(self, event_bus: EventBus, config_manager: ConfigManager) -> None:
        """
        Initialize the decision logger.
        
        Args:
            event_bus: The central communication backbone.
            config_manager: Source of versioned system configurations.
        """
        self._event_bus = event_bus
        self._config_manager = config_manager

    async def log_decision(
        self,
        trace_id: UUID,
        model_id: str,
        features: Dict[str, float],
        signal: float,
        decision: str
    ) -> bool:
        """
        Persist the full decision context to the global event stream.
        
        Args:
            trace_id: The correlation ID for the trade lifecycle.
            model_id: Identifier of the inference model used.
            features: Calculated input vector for the model.
            signal: Raw numerical score produced by the model.
            decision: Final action taken (e.g. BUY, SELL, HOLD).
            
        Returns:
            bool: True if context successfully published.
        """
        if not trace_id:
            logger.error("DECISION_TRACE_FAILURE | Missing trace_id for decision audit.")
            return False

        try:
            # 1. Capture the authoritative config version used for this decision
            config_version = self._config_manager.get_current_version()
            
            # 2. Build the immutable trace event
            event = DecisionTraceEvent(
                trace_id=trace_id,
                source="AlphaStrategy",
                payload=DecisionTracePayload(
                    model_id=model_id,
                    features=features,
                    signal=signal,
                    decision=decision,
                    config_version=config_version
                )
            )
            
            # 3. Publish to the EventBus (eventually reaches AuditStore)
            success = await self._event_bus.publish(event)
            if not success:
                logger.warning(f"DECISION_TRACE_DROPPED | trace_id: {trace_id}")
                
            return success
            
        except Exception as e:
            # 4. Critical Error Handling: Emit a DecisionError to halt the pipeline if required
            logger.error(f"DECISION_LOG_CRITICAL | trace_id: {trace_id} | Error: {e!s}")
            
            error_event = DecisionErrorEvent(
                trace_id=trace_id,
                source="DecisionLogger",
                payload=DecisionErrorPayload(
                    module_name="DecisionLogger",
                    error_type="COLLECTION_ERROR",
                    details=str(e)
                )
            )
            await self._event_bus.publish(error_event)
            return False
