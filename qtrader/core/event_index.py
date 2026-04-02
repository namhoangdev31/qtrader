from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class EventIndex:
    """
    High-performance in-memory index for the EventStore.
    Manages idempotency (event_id tracking) and monotonic offsets per partition.
    """

    def __init__(self) -> None:
        """
        Initialize the event index.
        """
        # Set of seen UUIDs for O(1) idempotency check
        self._event_ids: set[UUID] = set()
        
        # Mapping from partition_key to current monotonically increasing offset
        self._partition_offsets: dict[str, int] = {}

    def is_duplicate(self, event_id: UUID) -> bool:
        """
        Check if an event ID has already been persisted.
        """
        return event_id in self._event_ids

    def get_next_offset(self, partition: str) -> int:
        """
        Retrieve the next available offset for a specific partition.
        """
        return self._partition_offsets.get(partition, 0)

    def register_event(self, event_id: UUID, partition: str) -> int:
        """
        Mark an event as persisted and increment the partition's offset.
        
        Returns:
            int: The offset assigned to this event.
        """
        current_offset = self._partition_offsets.get(partition, 0)
        self._event_ids.add(event_id)
        self._partition_offsets[partition] = current_offset + 1
        return current_offset

    def clear(self) -> None:
        """Clear all indexed data."""
        self._event_ids.clear()
        self._partition_offsets.clear()

    @property
    def total_event_count(self) -> int:
        """Return the total number of unique events indexed."""
        return len(self._event_ids)

    def get_partition_stats(self) -> dict[str, int]:
        """Return a summary of offsets per partition."""
        return self._partition_offsets.copy()
