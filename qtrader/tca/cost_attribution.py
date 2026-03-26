from __future__ import annotations

from typing import TYPE_CHECKING

from qtrader.core.events import (
    AttributionErrorEvent,
    AttributionErrorPayload,
    CostAttributionEvent,
    CostAttributionPayload,
    EventType,
    ImplementationShortfallEvent,
    SlippageBreakdownEvent,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from uuid import UUID

    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import BaseEvent


class CostAttribution:
    """
    Senior Quantitative Analyst engine for granular cost attribution.

    Breaks down total implementation shortfall into contributing factors.
    """

    # Constants for numerical stability and validation
    ZERO_COST_THRESHOLD = 1e-9
    CONSISTENCY_TOLERANCE = 0.01

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the attribution engine with global bus access.
        """
        self._event_bus = event_bus

    async def attribute_lifecycle_costs(
        self, trace_id: UUID, events: list[BaseEvent]
    ) -> CostAttributionEvent | None:
        """
        Consolidate TCA events and attribute costs to sources.

        Args:
            trace_id: Global correlation ID for the trade.
            events: Chronological stream of events for the trace.
        """
        try:
            # 1. Extraction: Find core TCA diagnostic events
            is_event = next(
                (e for e in events if e.event_type == EventType.IMPLEMENTATION_SHORTFALL), None
            )
            slip_event = next(
                (e for e in events if e.event_type == EventType.SLIPPAGE_BREAKDOWN), None
            )

            # Funding might be separate per-ledger or inside metadata
            funding_cost = sum(
                e.payload.amount if hasattr(e.payload, "amount") else 0.0
                for e in events
                if e.event_type == EventType.FUNDING_CALCULATED
            )

            if not is_event or not isinstance(is_event, ImplementationShortfallEvent):
                await self._emit_error(
                    trace_id, "MISSING_IS_EVENT", "Total shortfall event not found."
                )
                return None

            if not slip_event or not isinstance(slip_event, SlippageBreakdownEvent):
                await self._emit_error(
                    trace_id, "MISSING_SLIPPAGE_BREAKDOWN", "Slippage breakdown not found."
                )
                return None

            # 2. Consolidation Logic
            # total_cost in IS payload already includes fees.
            total_shortfall = is_event.payload.total_cost
            total_cost = total_shortfall + funding_cost

            if abs(total_cost) < self.ZERO_COST_THRESHOLD:
                # Handle zero-cost edge case (e.g. perfect alignment or cancellation)
                return await self._emit_zero_attribution(trace_id)

            s_payload = slip_event.payload
            impact = s_payload.market_impact
            timing = s_payload.timing_cost
            fees = s_payload.fees

            # 3. Attribution: Compute Percentage Contribution
            impact_pct = impact / total_cost
            timing_pct = timing / total_cost
            fee_pct = fees / total_cost
            funding_pct = funding_cost / total_cost

            # 4. Persistence and Broadcasting
            event = CostAttributionEvent(
                trace_id=trace_id,
                source="CostAttributionEngine",
                payload=CostAttributionPayload(
                    trace_id=trace_id,
                    total_cost=total_cost,
                    impact_pct=impact_pct,
                    timing_pct=timing_pct,
                    fee_pct=fee_pct,
                    funding_pct=funding_pct,
                    metadata={
                        "is_sum_consistently": abs(
                            (impact + timing + fees + funding_cost) - total_cost
                        )
                        < self.CONSISTENCY_TOLERANCE
                    },
                ),
            )

            await self._event_bus.publish(event)
            logger.info(f"COSTS_ATTRIBUTED | trace_id: {trace_id} | Total: {total_cost:.2f}")

            return event

        except Exception as e:
            logger.error(f"COST_ATTRIBUTION_FAILURE | {e!s}")
            await self._emit_error(trace_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_zero_attribution(self, trace_id: UUID) -> CostAttributionEvent:
        event = CostAttributionEvent(
            trace_id=trace_id,
            source="CostAttributionEngine",
            payload=CostAttributionPayload(
                trace_id=trace_id,
                total_cost=0.0,
                impact_pct=0.0,
                timing_pct=0.0,
                fee_pct=0.0,
                funding_pct=0.0,
            ),
        )
        await self._event_bus.publish(event)
        return event

    async def _emit_error(self, trace_id: UUID, err_type: str, details: str) -> None:
        error_event = AttributionErrorEvent(
            trace_id=trace_id,
            source="CostAttributionEngine",
            payload=AttributionErrorPayload(error_type=err_type, details=details),
        )
        await self._event_bus.publish(error_event)
