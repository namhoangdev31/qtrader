from __future__ import annotations

from typing import Any

from loguru import logger


class Arbitrator:
    """Handles A/B feed arbitration to select the best market data source.
    
    In high-availability setups, the same symbol might be received from multiple feeds.
    The Arbitrator ensures only the highest priority or first-arriving unique event
    passes through, preventing duplicate processing.
    """

    def __init__(self, primary_feed: str = "A") -> None:
        self.primary_feed = primary_feed
        self._last_seq_per_feed: dict[str, dict[str, int]] = {}  # feed -> symbol -> last_seq

    def handle(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Process a raw feed event and decide if it should continue.
        
        Args:
            event: Raw dictionary from a data source. Expects 'feed' and 'symbol' keys.
            
        Returns:
            The event if it passes arbitration, or None if it should be dropped.
        """
        feed = event.get("feed", "A")
        symbol = event.get("symbol", "unknown")
        seq_id = event.get("seq_id", 0)

        # Basic A/B arbitration: If it's from the primary feed, we usually take it.
        # If it's from a secondary feed, we only take it if the primary is lagging or down.
        # For now, we implement a simple deduplication and priority logic.
        
        if feed not in self._last_seq_per_feed:
            self._last_seq_per_feed[feed] = {}
        
        last_seq = self._last_seq_per_feed[feed].get(symbol, -1)
        
        if seq_id <= last_seq:
            logger.debug(f"Arbitrator: Dropping duplicate/older event from {feed}:{symbol} (seq {seq_id} <= {last_seq})")
            return None
        
        self._last_seq_per_feed[feed][symbol] = seq_id
        
        # In a more advanced version, we would cross-check feeds A and B here.
        # If feed B arrives before A but with the same seq_id, we might buffer or emit.
        
        return event
