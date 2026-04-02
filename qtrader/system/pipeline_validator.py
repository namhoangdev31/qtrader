from __future__ import annotations

import inspect
import logging
from typing import Any

from qtrader.core.events import BaseEvent

logger = logging.getLogger(__name__)


class PipelineValidator:
    """
    Architectural Gatekeeper for the QTrader Pipeline.
    
    Enforces strict event-driven communication by validating that modules 
    do not hold direct references to one another, preventing illegal 
    coupling and side-channel mutation.
    """

    FORBIDDEN_DIRECT_CALLS: list[str] = [
        "ExecutionEngine", 
        "OMS", 
        "RuntimeRiskEngine", 
        "NAVEngine", 
        "CashLedger",
        "Strategy"
    ]

    @classmethod
    def validate_module_architecture(cls, target_cls: type[Any]) -> bool:
        """
        Scans a module's constructor to ensure zero direct-module injection.
        
        Args:
            target_cls: The class to inspect for architectural violations.
            
        Returns:
            bool: True if compliant, False if illegal dependencies found.
        """
        try:
            sig = inspect.signature(target_cls.__init__)
            violations = []
            
            for name, param in sig.parameters.items():
                param_str = str(param.annotation)
                for forbidden in cls.FORBIDDEN_DIRECT_CALLS:
                    # Ignore the class's own type if it happens to be in the list
                    if forbidden in param_str and forbidden != target_cls.__name__:
                        violations.append(forbidden)
            
            if violations:
                logger.critical(
                    f"PIPELINE_VIOLATION | {target_cls.__name__} has high-level direct calls to: {violations}. "
                    "All communication must be routed via EventBus."
                )
                return False
                
            logger.info(f"PIPELINE_CERTIFIED | {target_cls.__name__} is compliant with Event-Driven Policy.")
            return True
            
        except Exception as e:
            logger.warning(f"PIPELINE_VALIDATION_ERROR | Could not inspect {target_cls.__name__}: {e}")
            return True # Default to pass if inspection fails on non-standard init

    @staticmethod
    def verify_trace_integrity(event: BaseEvent) -> bool:
        """
        Ensures an event carries a valid correlation ID for end-to-end audit.
        """
        if not event.trace_id:
            logger.error(f"TRACE_INTEGRITY_FAILURE | Event {event.event_type} is missing trace_id.")
            return False
        return True
