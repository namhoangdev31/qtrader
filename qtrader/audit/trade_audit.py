from __future__ import annotations

from typing import Any
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict

from qtrader.core.events import (
    BaseEvent,
    EventType,
    FillEvent,
    NAVEvent,
)
from qtrader.core.logger import log as logger


class TradeAuditRecord(BaseModel):
    """
    Authoritative summary of a trade's end-to-end lifecycle.
    
    Links disparate events (Signal -> Order -> Risk -> Execution -> PnL) 
    through a unified trace_id for deterministic reconstruction.
    """
    model_config = ConfigDict(frozen=True)

    trace_id: UUID
    symbol: str
    decision_time: int  # Microseconds since epoch (t_signal)
    execution_time: int | None = None  # t_exec
    executed_price: float | None = None
    pnl: float = 0.0
    status: str  # COMPLETED, INCOMPLETE, REJECTED


class TradeAudit:
    """
    Senior Audit Engine responsible for trade lifecycle reconstruction.
    """

    def build(self, events: list[BaseEvent]) -> TradeAuditRecord:
        """
        Reconstruct a full trade lifecycle from a sequence of events.
        """
        if not events:
            raise ValueError("Reconstruction requires a non-empty event stream.")

        sorted_events = sorted(events, key=lambda x: x.timestamp)
        
        trace_id = sorted_events[0].trace_id
        symbol = "UNKNOWN"
        decision_time = sorted_events[0].timestamp
        execution_time: int | None = None
        executed_price: float | None = None
        pnl = 0.0
        status = "INCOMPLETE"

        # Intermediate reconstruction state
        has_execution = False
        buy_price = 0.0
        sell_price = 0.0
        quantity = 0.0
        cost = 0.0

        for event in sorted_events:
            symbol = self._extract_symbol(event) or symbol

            if event.event_type == EventType.SIGNAL:
                decision_time = event.timestamp
            elif event.event_type == EventType.RISK_REJECTED:
                status = "REJECTED"
            elif event.event_type == EventType.FILL and isinstance(event, FillEvent):
                has_execution = True
                execution_time = event.timestamp
                executed_price = event.payload.price
                quantity = event.payload.quantity
                cost += event.payload.commission
                if event.payload.side == "BUY":
                    buy_price = executed_price
                else:
                    sell_price = executed_price
                status = "COMPLETED"
            elif event.event_type == EventType.NAV_UPDATED and isinstance(event, NAVEvent):
                pnl = event.payload.realized_pnl

        if has_execution and pnl == 0.0:
            pnl = self.compute_pnl(buy_price, sell_price, quantity, cost)

        if not has_execution and status != "REJECTED":
            logger.warning(f"AUDIT_GAP | trace_id: {trace_id} | Missing execution.")
            status = "INCOMPLETE"

        return TradeAuditRecord(
            trace_id=trace_id,
            symbol=symbol,
            decision_time=decision_time,
            execution_time=execution_time,
            executed_price=executed_price,
            pnl=pnl,
            status=status
        )

    def _extract_symbol(self, event: BaseEvent) -> str | None:
        """Helper to extract symbol from various event structures."""
        if hasattr(event, "symbol"):
            return str(event.symbol)
        payload: Any = getattr(event, "payload", None)
        if payload and hasattr(payload, "symbol"):
            return str(payload.symbol)
        return None

    def compute_pnl(self, buy: float, sell: float, qty: float, cost: float) -> float:
        """Mathematical model: PnL = (sell_price - buy_price) * quantity - cost"""
        return (sell - buy) * qty - cost

    def execution_latency(self, t_exec: int, t_signal: int) -> int:
        """Calculate execution latency in microseconds."""
        return t_exec - t_signal
