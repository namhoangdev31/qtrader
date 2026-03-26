from __future__ import annotations

import datetime
from typing import Any

from loguru import logger

from qtrader.core.config import Config
from qtrader.core.event import DataErrorEvent, EventType, FeedEvent
from qtrader.core.event_bus import EventBus


class FeedArbitrator:
    """Deterministic A/B feed selector based on latency and staleness.
    
    Attributes:
        feed_switch_count: Number of times the selected source has changed.
        last_selected_source: The source name of the last selected event.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self.feed_switch_count = 0
        self.last_selected_source: str | None = None
        
        # Load weights from config to avoid magic numbers
        self.w1 = float(Config.arbitrator_wt_latency)
        self.w2 = float(Config.arbitrator_wt_staleness)

    def score(self, event: FeedEvent) -> float:
        """Compute the arbitration score for a feed event.
        
        Score = w1 * latency + w2 * staleness
        
        Args:
            event: The FeedEvent to score.
            
        Returns:
            The calculated score (lower is better).
        """
        # Staleness is the age of the event in milliseconds
        now = datetime.datetime.now(datetime.timezone.utc)
        staleness = (now - event.timestamp).total_seconds() * 1000.0
        
        score = (self.w1 * event.latency) + (self.w2 * staleness)
        return float(score)

    async def select(self, feedA: FeedEvent | None, feedB: FeedEvent | None) -> FeedEvent | None:
        """Select the best feed event using the scoring model.
        
        Args:
            feedA: Event from source A.
            feedB: Event from source B.
            
        Returns:
            The selected FeedEvent, or None if both fail.
        """
        # 1. Handle missing feeds -> fallback to available
        if feedA is None and feedB is None:
            logger.error("FeedArbitrator: Both feeds are missing/null.")
            await self._emit_data_error("Both feeds missing", source="FeedArbitrator")
            return None
            
        if feedA is None:
            return self._finalize_selection(feedB)  # type: ignore (checked above)
            
        if feedB is None:
            return self._finalize_selection(feedA)
            
        # 2. Score feeds and select minimum
        scoreA = self.score(feedA)
        scoreB = self.score(feedB)
        
        selected = feedA if scoreA <= scoreB else feedB
        return self._finalize_selection(selected)

    def _finalize_selection(self, event: FeedEvent) -> FeedEvent:
        """Update observability metrics and return the selected event."""
        if self.last_selected_source and self.last_selected_source != event.source:
            self.feed_switch_count += 1
            logger.info(
                f"FeedArbitrator: Source switched from {self.last_selected_source} to {event.source}. "
                f"Total switches: {self.feed_switch_count}"
            )
            
        self.last_selected_source = event.source
        return event

    async def _emit_data_error(self, message: str, source: str) -> None:
        """Emit a DataErrorEvent to the event bus."""
        if not self.event_bus:
            return
            
        error_event = DataErrorEvent(
            type=EventType.DATA_ERROR,
            source=source,
            message=message,
            severity="CRITICAL",
        )
        await self.event_bus.publish(EventType.DATA_ERROR, error_event)

    def report(self) -> dict[str, Any]:
        """Generate the arbitration status report."""
        return {
            "status": "active" if self.last_selected_source else "idle",
            "summary": "Feed arbitration active",
            "metrics": {
                "feed_switch_count": self.feed_switch_count,
                "current_source": self.last_selected_source
            }
        }
