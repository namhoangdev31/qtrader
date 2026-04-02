from __future__ import annotations

import json
import logging
import os
from typing import Protocol

from qtrader.core.event_factory import EventFactory
from qtrader.core.event_index import EventIndex
from qtrader.core.events import BaseEvent

logger = logging.getLogger(__name__)


class BaseEventStore(Protocol):
    """
    Protocol for persistent event logging.
    Enables deterministic replay and recovery of system state.
    """

    async def append(self, event: BaseEvent) -> int | None:
        """Persist an event to stable storage. Returns offset if new, None if duplicate."""
        ...

    async def get_events(
        self, 
        partition: str | None = None,
        start_offset: int | None = None, 
        end_offset: int | None = None
    ) -> list[BaseEvent]:
        """Retrieve events based on partition and offset range for replay."""
        ...

    async def get_events_by_trace_id(self, trace_id: str | UUID) -> list[BaseEvent]:
        """Retrieve all events across all partitions sharing a common trace_id."""
        ...


class FileEventStore:
    """
    Partitioned append-only file storage for events.
    Uses JSONLine format with per-partition logs and an in-memory index for idempotency.
    """

    def __init__(self, base_path: str = "data/event_store"):
        """
        Initialize the partitioned event store.
        
        Args:
            base_path: Root directory for event logs and partitions.
        """
        self.base_path = base_path
        self.partitions_dir = os.path.join(base_path, "partitions")
        os.makedirs(self.partitions_dir, exist_ok=True)
        
        self._index = EventIndex()
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """
        Scan all partition logs on startup to rebuild the idempotency index.
        Ensures consistency across restarts with zero double-writes.
        """
        logger.info("Rebuilding EventStore index from logs...")
        if not os.path.exists(self.partitions_dir):
            return

        for filename in os.listdir(self.partitions_dir):
            if filename.endswith(".jsonl"):
                filepath = os.path.join(self.partitions_dir, filename)
                
                try:
                    with open(filepath, encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                event_data = json.loads(line)
                                event = EventFactory.from_dict(event_data)
                                p_key = event.partition_key or "default"
                                self._index.register_event(event.event_id, p_key)
                            except Exception as e:
                                logger.warning(f"Metadata corruption in {filename}: {e}")
                except Exception as e:
                    logger.error(f"Failed to scan partition log {filename}: {e}")
                    
        logger.info(f"Index rebuild complete. Total events indexed: {self._index.total_event_count}")

    async def append(self, event: BaseEvent) -> int | None:
        """
        Append an event to its partition log if it's not a duplicate.
        
        Returns:
            int | None: The offset assigned to the event, or None if it was an idempotent skip.
        """
        # 1. Idempotency Check
        if self._index.is_duplicate(event.event_id):
            logger.debug(f"Idempotent skip for event {event.event_id}")
            return None

        # 2. Partition Routing
        partition_key = event.partition_key or "default"
        
        # 3. Assign Offset and Update Index
        offset = self._index.register_event(event.event_id, partition_key)
        
        # 4. Prepare Persisted Event (add offset metadata)
        # Using model_copy to maintain immutability of the incoming event object
        persisted_event = event.model_copy(update={"offset": offset})
        event_json = persisted_event.model_dump_json()

        # 5. Atomic Append to Partition File
        safe_partition_key = partition_key.replace("/", "_").replace("\\", "_")
        filepath = os.path.join(self.partitions_dir, f"{safe_partition_key}.jsonl")
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(event_json + "\n")
                f.flush()
                # Ensure data is committed to disk for HFT reliability
                os.fsync(f.fileno())
            return offset
        except Exception as e:
            logger.error(f"Critical storage failure for event {event.event_id}: {e}")
            # Note: In production, we'd emit a StorageErrorEvent here
            raise

    async def get_events(
        self, 
        partition: str | None = None,
        start_offset: int | None = None, 
        end_offset: int | None = None
    ) -> list[BaseEvent]:
        """
        Retrieve events from a specific partition based on an offset range.
        If partition is None, reads across all partitions (ordered only by local offset).
        """
        events = []
        
        # Determine which logs to read
        if partition:
            safe_partition = partition.replace("/", "_").replace("\\", "_")
            files_to_read = [f"{safe_partition}.jsonl"]
        else:
            files_to_read = [f for f in os.listdir(self.partitions_dir) if f.endswith(".jsonl")]

        for filename in files_to_read:
            filepath = os.path.join(self.partitions_dir, filename)
            if not os.path.exists(filepath):
                continue

            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    try:
                        # Reconstruct specialized event subclass via factory
                        event = EventFactory.from_dict(json.loads(line))
                        
                        # Apply offset filters with safety guards
                        if (start_offset is not None and event.offset is not None 
                            and event.offset < start_offset):
                            continue
                        if (end_offset is not None and event.offset is not None 
                            and event.offset > end_offset):
                            continue
                            
                        events.append(event)
                    except Exception:
                        continue
                        
        # Default sort by global timestamp for cross-partition queries
        return sorted(events, key=lambda x: x.timestamp)

    async def get_events_by_trace_id(self, trace_id: str | UUID) -> list[BaseEvent]:
        """
        Scan all partitions for a specific trace_id.
        This enables cross-functional forensic analysis of a single trade lifecycle.
        """
        events: list[BaseEvent] = []
        target_trace = str(trace_id)
        
        if not os.path.exists(self.partitions_dir):
            return []

        # Optimization: scan all .jsonl partition logs
        for filename in os.listdir(self.partitions_dir):
            if not filename.endswith(".jsonl"):
                continue
            
            filepath = os.path.join(self.partitions_dir, filename)
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    try:
                        # Pre-check for trace_id before full Pydantic parsing
                        if target_trace not in line:
                            continue
                            
                        event = EventFactory.from_dict(json.loads(line))
                        if str(event.trace_id) == target_trace:
                            events.append(event)
                    except Exception:
                        continue
                        
        return sorted(events, key=lambda x: x.timestamp)
