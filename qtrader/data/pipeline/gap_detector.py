from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.events import EventType, GapDetectedEvent

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.oms.event_store import EventStore


class GapDetector:
    """Detects sequence discontinuities in market data streams.
    
    A gap is defined as any sequence ID that is not (last_sequence + 1).
    This stage is stateless: it fetches the last known sequence from the EventStore.
    """

    def __init__(self, event_store: EventStore, event_bus: EventBus | None = None) -> None:
        self.event_store = event_store
        self.event_bus = event_bus

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """Check for sequence gaps in the incoming event.
        
        Args:
            event: Canonical MarketEvent dict.
            
        Returns:
            The event, potentially tagged with gap metadata if a skip is detected.
        """
        symbol = event.get("symbol", "unknown")
        seq_id = event.get("seq_id", 0)
        
        # 1. Fetch last known sequence for this symbol from EventStore
        # Note: EventStore must provide a fast (indexed or in-memory) lookup for head sequence.
        last_seq = self.event_store.get_last_sequence(symbol)
        
        # 2. Sequence Validation
        if last_seq > 0:
            expected = last_seq + 1
            if seq_id != expected:
                gap_size = seq_id - expected
                logger.warning(
                    f"GapDetector: Sequence mismatch for {symbol}. "
                    f"Expected {expected}, got {seq_id} (Gap: {gap_size})"
                )
                
                # Tag the event to trigger the Recovery stage
                metadata = event.setdefault("metadata", {})
                metadata["gap_detected"] = True
                metadata["expected_seq"] = expected
                metadata["received_seq"] = seq_id
                
                # Emit GapDetectedEvent
                if self.event_bus:
                    gap_event = GapDetectedEvent(
                        event_id=str(uuid.uuid4()),
                        trace_id=event.get("trace_id", "pending"),
                        symbol=symbol,
                        expected_seq=expected,
                        received_seq=seq_id,
                    )
                    await self.event_bus.publish(EventType.GAP_DETECTED, gap_event)
                    
        return event
