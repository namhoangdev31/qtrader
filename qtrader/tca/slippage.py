from __future__ import annotations

import json
from typing import TYPE_CHECKING

from qtrader.core.events import (
    DecisionTraceEvent,
    EventType,
    FillEvent,
    SlippageBreakdownEvent,
    SlippageBreakdownPayload,
    TCAWarningEvent,
    TCAWarningPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from uuid import UUID

    from qtrader.audit.audit_store import AuditStore
    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import BaseEvent


class SlippageDecomposition:
    """
    Quantitative Execution Analyst engine for slippage decomposition.
    
    Breaks down total execution slippage into timing and impact components.
    """

    def __init__(self, event_bus: EventBus, audit_store: AuditStore) -> None:
        """
        Initialize the decomposition engine with data source and bus hooks.
        """
        self._event_bus = event_bus
        self._audit_store = audit_store

    async def decompose_trace(
        self, 
        trace_id: UUID, 
        events: list[BaseEvent]
    ) -> SlippageBreakdownEvent | None:
        """
        Perform forensic decomposition of slippage for a specific trade lifecycle.
        
        Args:
            trace_id: Global correlation ID for the trade.
            events: Chronological stream of events for the trace.
        """
        try:
            # 1. Identification: Extract the Decision benchmark and fills
            decision_event = next(
                (e for e in events if e.event_type == EventType.DECISION_TRACE), None
            )
            fill_events = [
                e for e in events if e.event_type == EventType.FILL and isinstance(e, FillEvent)
            ]

            if not decision_event or not isinstance(decision_event, DecisionTraceEvent):
                return None

            if not fill_events:
                return None

            d_payload = decision_event.payload
            decision_price = d_payload.decision_price
            side = d_payload.decision
            symbol = self._extract_symbol(fill_events)
            
            # Side multiplier (Buy: +1, Sell: -1)
            m = 1.0 if side == "BUY" else -1.0
            
            total_impact = 0.0
            total_timing = 0.0
            total_fees = 0.0
            total_qty = 0.0
            
            for fill in fill_events:
                f_payload = fill.payload
                qty = f_payload.quantity
                fill_price = f_payload.price
                fill_time = fill.timestamp
                
                # 2. Market Context Retrieval: Find mid-price AT execution time
                mid_price = await self._get_mid_price(symbol, fill_time)
                
                if mid_price is None:
                    # Emit a warning and skip breakdown for this trace
                    msg = f"Missing mid-price for {symbol} at {fill_time}"
                    await self._emit_warning(trace_id, msg)
                    return None

                # 3. Decomposition Logic
                # Impact = (ExecPrice - Mid) * Side
                impact = (fill_price - mid_price) * m * qty
                # Timing = (Mid - DecisionPrice) * Side
                timing = (mid_price - decision_price) * m * qty
                
                total_impact += impact
                total_timing += timing
                total_fees += f_payload.commission
                total_qty += qty

            total_slippage = total_impact + total_timing + total_fees

            # 4. Persistence and Broadcasting
            avg_impact_bps = 0.0
            if total_qty > 0:
                avg_impact_bps = (total_impact / (total_qty * decision_price)) * 10000

            event = SlippageBreakdownEvent(
                trace_id=trace_id,
                source="SlippageDecompositionEngine",
                payload=SlippageBreakdownPayload(
                    trace_id=trace_id,
                    total_slippage=total_slippage,
                    market_impact=total_impact,
                    timing_cost=total_timing,
                    fees=total_fees,
                    metadata={
                        "symbol": symbol,
                        "avg_impact_bps": avg_impact_bps
                    }
                )
            )
            
            await self._event_bus.publish(event)
            logger.info(
                f"SLIPPAGE_DECOMPOSED | trace_id: {trace_id} | "
                f"Impact: {total_impact:.2f} Timing: {total_timing:.2f}"
            )
            
            return event

        except Exception as e:
            logger.error(f"SLIPPAGE_DECOMP_FAILURE | {e!s}")
            return None

    async def _get_mid_price(self, symbol: str, timestamp_us: int) -> float | None:
        """Query the analytical store for the mid-price nearest to the timestamp."""
        # Note: timestamp_us is a validated integer from the event.
        sql = f"""
            SELECT payload_json
            FROM audit_events
            WHERE event_type = 'MARKET_DELTA' 
              AND timestamp_us <= {timestamp_us}
            ORDER BY timestamp_us DESC
            LIMIT 1
        """  # noqa: S608
        
        df = self._audit_store.query_olap(sql)
        if df.is_empty():
            return None
            
        try:
            payload = json.loads(df["payload_json"][0])
            bids = payload["payload"]["bids"]
            asks = payload["payload"]["asks"]
            if bids and asks:
                return float((bids[0][0] + asks[0][0]) / 2.0)
            return None
        except (KeyError, IndexError, json.JSONDecodeError, TypeError):
            return None

    def _extract_symbol(self, fill_events: list[FillEvent]) -> str:
        return fill_events[0].payload.symbol

    async def _emit_warning(self, trace_id: UUID, message: str) -> None:
        event = TCAWarningEvent(
            trace_id=trace_id,
            source="SlippageDecompositionEngine",
            payload=TCAWarningPayload(trace_id=trace_id, message=message)
        )
        await self._event_bus.publish(event)
