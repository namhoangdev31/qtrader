import json
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum


class EventStore:
    """High-fidelity persistence layer for system events.
    
    Supports the fundamental architectural requirement: State(t) = Σ Events[0 → t].
    Ensures that for every order, the entire trace of transitions is preserved.
    """

    def __init__(self, log_path: str = "data/events/order_event_log.jsonl") -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._log = logging.getLogger("qtrader.oms.event_store")

    async def record_event(self, event: Any) -> None:
        """Append a state-changing event to the persistent log."""
        try:
            event_dict = self._serialize(event)
            event_dict["timestamp"] = datetime.utcnow().isoformat()
            
            with open(self.log_path, "a") as f:
                f.write(json.dumps(event_dict) + "\n")
        except Exception as e:
            self._log.exception("Persistent event logging failed", exc_info=e)

    def replay_order(self, order_id: str) -> list[dict[str, Any]]:
        """Replay events for a specific order to reconstruct its state."""
        if not os.path.exists(self.log_path):
            return []
            
        trace = []
        with open(self.log_path, "r") as f:
            for line in f:
                ev = json.loads(line)
                # Some events have 'order_id' at root, some in nested 'order'
                target_id = ev.get("order_id") or (ev.get("order") or {}).get("order_id")
                if target_id == order_id:
                    trace.append(ev)
        return trace

    def _serialize(self, obj: Any) -> dict[str, Any]:
        """Deep serialization for events with Decimals/Enums."""
        if is_dataclass(obj):
            return {k: self._serialize(v) for k, v in asdict(obj).items()}
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize(v) for v in obj]
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Enum):
            return obj.value if hasattr(obj, 'value') else obj.name
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
