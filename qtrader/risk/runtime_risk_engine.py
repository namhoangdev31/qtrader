from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional, Union

from qtrader.core.events import (
    OrderEvent, 
    RiskApprovedEvent, 
    RiskRejectedEvent, 
    RiskApprovedPayload, 
    RiskRejectedPayload
)
from qtrader.core.state_store import SystemState
from qtrader.risk.constraints import RiskConstraint, RiskResult

logger = logging.getLogger(__name__)


class RuntimeRiskEngine:
    """
    Real-Time Hard-Gate Risk Engine.
    
    This engine acts as a mandatory gate for all order execution. It evaluates 
    every OrderEvent against a set of deterministic, hard constraints based 
    on the platform's current SystemState.
    
    Architecture:
    - **Hard Gating**: Only RiskApprovedEvents allow the execution engine to proceed.
    - **Fail-Safe Mode**: Rejects all orders if internal computation errors occur.
    - **Sub-ms Latency**: Designed to run entirely in-memory with pre-computed snapshots.
    """

    def __init__(self, constraints: Optional[List[RiskConstraint]] = None) -> None:
        """
        Initialize the RuntimeRiskEngine.
        
        Args:
            constraints: Initial list of risk rules to enforce.
        """
        self._constraints = constraints or []

    def register_rule(self, constraint: RiskConstraint) -> None:
        """
        Add a new active risk rule to the hard gate.
        
        Rules are applied in the order they were registered.
        """
        self._constraints.append(constraint)

    def evaluate(self, order: OrderEvent, state: SystemState) -> Union[RiskApprovedEvent, RiskRejectedEvent]:
        """
        Evaluate an order for risk compliance.
        
        Iterates through all registered rules. The FIRST violation triggers an 
        immediate RiskRejectedEvent. All rules must approve for a RiskApprovedEvent.
        
        Args:
            order: The incoming trade request from a strategy.
            state: The latest authoritative system state snapshot.
            
        Returns:
            Union[RiskApprovedEvent, RiskRejectedEvent]: The deterministic decision.
        """
        try:
            # 1. Pipeline Check against registered hard rules
            for rule in self._constraints:
                # Every rule must be sub-ms (deterministic accounting or matrix math)
                result = rule.validate(order, state)
                
                # Hard Rejection Logic: NO BYPASS
                if not result.approved:
                    logger.warning(
                        f"RISK_REJECTED | Order: {order.payload.order_id} | "
                        f"Reason: {result.reason} | Metric: {result.metric_value:.2f}"
                    )
                    
                    return RiskRejectedEvent(
                        trace_id=order.trace_id,
                        source="RuntimeRiskEngine",
                        payload=RiskRejectedPayload(
                            order_id=order.payload.order_id,
                            reason=result.reason or "UNDEFINED_VIOLATION",
                            metric_value=float(result.metric_value),
                            threshold=float(result.threshold)
                        )
                    )
            
            # 2. All Constraints Satisfied
            logger.info(f"RISK_APPROVED | Order: {order.payload.order_id}")
            return RiskApprovedEvent(
                trace_id=order.trace_id,
                source="RuntimeRiskEngine",
                payload=RiskApprovedPayload(
                    order_id=order.payload.order_id
                )
            )
            
        except Exception as e:
            # 3. Fail-Safe Mode: Reject order if engine logic itself fails
            logger.critical(
                f"RISK_ENGINE_FAILURE | Order: {order.payload.order_id} | "
                f"Halting order due to error: {e!s}"
            )
            
            return RiskRejectedEvent(
                trace_id=order.trace_id,
                source="RuntimeRiskEngine",
                payload=RiskRejectedPayload(
                    order_id=order.payload.order_id,
                    reason=f"ENGINE_COMPUTE_ERROR: {e!s}",
                    metric_value=0.0,
                    threshold=0.0
                )
            )
