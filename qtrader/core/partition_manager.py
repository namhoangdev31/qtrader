from __future__ import annotations

import hashlib

from qtrader.core.events import BaseEvent


class PartitionManager:
    """
    Handles event routing to deterministic partitions.
    Ensures that events with the same key (e.g., symbol or order_id) 
    are always routed to the same worker to maintain strict ordering.
    """

    def __init__(self, num_partitions: int = 16):
        """
        Initialize the partition manager.
        
        Args:
            num_partitions: The fixed number of virtual partitions.
        """
        self.num_partitions = num_partitions

    def get_partition_key(self, event: BaseEvent) -> str:
        """
        Extract the partition key from an event.
        Priority: symbol > order_id > default.
        """
        payload = event.payload
        
        # Check if payload is a Pydantic model or dataclass
        if hasattr(payload, "symbol") and payload.symbol:
            return str(payload.symbol)
        if hasattr(payload, "order_id") and payload.order_id:
            return str(payload.order_id)
            
        # Fallback to dict access if payload is a raw dict
        if isinstance(payload, dict):
            key = payload.get("symbol") or payload.get("order_id")
            if key:
                return str(key)
                
        # System events or events without keys go to a default partition
        return "system_default"

    def get_partition_index(self, event: BaseEvent) -> int:
        """
        Map an event to a specific partition index using deterministic hashing.
        """
        key = self.get_partition_key(event)
        
        # Use MD5 for deterministic hashing across any environment
        hash_val = hashlib.md5(key.encode()).hexdigest()
        return int(hash_val, 16) % self.num_partitions
