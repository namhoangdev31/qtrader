from __future__ import annotations

from typing import TYPE_CHECKING

from qtrader.core.events import (
    DecisionTraceEvent,
    EventType,
    FillEvent,
    ImplementationShortfallEvent,
    ImplementationShortfallPayload,
    TCAErrorEvent,
    TCAErrorPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from uuid import UUID

    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import BaseEvent


class ImplementationShortfall:
    """
    Principal Transaction Cost Analysis (TCA) Engine.

    Measures execution efficiency by calculating the Implementation Shortfall (IS):
    the difference between the theoretical decision benchmark and actual fills.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the TCA engine with system hooks.
        """
        self._event_bus = event_bus

    async def compute_and_emit(
        self, trace_id: UUID, events: list[BaseEvent]
    ) -> ImplementationShortfallEvent | None:
        """
        Calculate and broadcast the implementation shortfall for a specific trade lifecycle.

        Args:
            trace_id: Global correlation ID for the trade.
            events: Chronological stream of events for the trace.

        Returns:
            Optional ImplementationShortfallEvent if computed successfully.
        """
        try:
            # 1. Extraction: Find the Decision benchmark and the execution fills
            decision_event = next(
                (e for e in events if e.event_type == EventType.DECISION_TRACE), None
            )
            fill_events = [
                e for e in events if e.event_type == EventType.FILL and isinstance(e, FillEvent)
            ]

            if not decision_event or not isinstance(decision_event, DecisionTraceEvent):
                await self._emit_error(
                    trace_id, "MISSING_DECISION", "DecisionTraceEvent not found."
                )
                return None

            if not fill_events:
                logger.warning(f"TCA_INCOMPLETE | trace_id: {trace_id} | No fill events found.")
                return None

            # 2. Calculation: Aggregate across all fills in the lifecycle
            d_payload = decision_event.payload
            decision_price = d_payload.decision_price
            side = d_payload.decision

            total_shortfall = 0.0
            total_qty = 0.0
            total_commission = 0.0
            weighted_fill_price = 0.0

            for fill in fill_events:
                f_payload = fill.payload
                qty = f_payload.quantity
                price = f_payload.price

                # Direction-aware IS calculation
                if side == "BUY":
                    shortfall = (price - decision_price) * qty
                elif side == "SELL":
                    shortfall = (decision_price - price) * qty
                else:
                    shortfall = 0.0

                total_shortfall += shortfall
                total_qty += qty
                total_commission += f_payload.commission
                weighted_fill_price += price * qty

            avg_fill_price = weighted_fill_price / total_qty if total_qty > 0 else 0.0
            total_cost = total_shortfall + total_commission

            # 3. Notification: Materialize result and broadcast to audit systems
            is_event = ImplementationShortfallEvent(
                trace_id=trace_id,
                source="TCAEngine",
                payload=ImplementationShortfallPayload(
                    trace_id=trace_id,
                    decision_price=decision_price,
                    executed_price=avg_fill_price,
                    quantity=total_qty,
                    shortfall=total_shortfall,
                    total_cost=total_cost,
                    side=side,
                    metadata={"fill_count": len(fill_events), "total_commission": total_commission},
                ),
            )

            await self._event_bus.publish(is_event)
            logger.info(f"TCA_COMPUTED | trace_id: {trace_id} | IS: {total_shortfall:.4f}")

            return is_event

        except Exception as e:
            logger.error(f"TCA_FAILURE | trace_id: {trace_id} | {e!s}")
            await self._emit_error(trace_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, trace_id: UUID, err_type: str, details: str) -> None:
        """Helper to broadcast TCA system failures."""
        error_event = TCAErrorEvent(
            trace_id=trace_id,
            source="TCAEngine",
            payload=TCAErrorPayload(
                error_type=err_type, details=details, metadata={"trace_id": str(trace_id)}
            ),
        )
        await self._event_bus.publish(error_event)
