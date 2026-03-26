from __future__ import annotations

from typing import Any

from loguru import logger

from qtrader.core.event import EventType, GapDetectedEvent
from qtrader.core.event_bus import EventBus
from qtrader.oms.event_store import EventStore


class GapDetector:
    """Monitors sequence IDs to identify discontinuities in market data streams.
    
    This implementation is entirely stateless, relying on the `EventStore`
    to retrieve the expected sequence for each symbol.
    """

    def __init__(self, event_store: EventStore, event_bus: EventBus | None = None) -> None:
        self.event_store = event_store
        self.event_bus = event_bus

    async def handle(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Inspect the event for sequence gaps against the persistent EventStore.
        
        Args:
            event: Raw event dict from Arbitration.
            
        Returns:
            The event if valid, or signals recovery if a gap is detected.
        """
        if not event:
            return None
            
        symbol = event.get("symbol", "unknown")
        seq_id = event.get("seq_id", 0)

        if seq_id == 0:
            return event
            
        # Stateless fetch of expected sequence
        last_seq = self.event_store.get_last_sequence(symbol)
        
        # Initial check (Gap == 1 is valid)
        if last_seq > 0:
            expected = last_seq + 1
            if seq_id != expected:
                gap_size = seq_id - expected
                logger.warning(
                    f"GapDetector: Sequence mismatch for {symbol}. Expected {expected}, got {seq_id} (Gap: {gap_size})"
                )
                
                # Emit GapDetectedEvent
                if self.event_bus:
                    import uuid
                    gap_event = GapDetectedEvent(
                        event_id=str(uuid.uuid4()),
                        trace_id=event.get("trace_id", "pending"),
                        symbol=symbol,
                        expected_seq=expected,
                        received_seq=seq_id,
                    )
                    await self.event_bus.publish(EventType.GAP_DETECTED, gap_event)
                
                # Tag event for Recovery stage
                if "metadata" not in event:
                    event["metadata"] = {}
                event["metadata"]["gap_detected"] = True
                event["metadata"]["expected_seq"] = expected
                event["metadata"]["received_seq"] = seq_id
        
        return event

    def reset_for_symbol(self, symbol: str) -> None:
        """Reset sequence tracker for a symbol (e.g., after a manual recovery)."""
        if symbol in self._last_seq_id:
            del self._last_seq_id[symbol]
