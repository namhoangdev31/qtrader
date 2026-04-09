from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.core.events import BaseEvent


class PartitionManager:
    def __init__(self, num_partitions: int = 16) -> None:
        self.num_partitions = num_partitions

    def get_partition_key(self, event: BaseEvent) -> str:
        payload = event.payload
        if hasattr(payload, "symbol") and payload.symbol:
            return str(payload.symbol)
        if hasattr(payload, "order_id") and payload.order_id:
            return str(payload.order_id)
        if isinstance(payload, dict):
            key = payload.get("symbol") or payload.get("order_id")
            if key:
                return str(key)
        return "system_default"

    def get_partition_index(self, event: BaseEvent) -> int:
        key = self.get_partition_key(event)
        hash_val = hashlib.md5(key.encode()).hexdigest()
        return int(hash_val, 16) % self.num_partitions
