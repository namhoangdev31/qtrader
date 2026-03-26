import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from qtrader.core.event import EventType
from qtrader.core.types import EventBusProtocol

_LOG = logging.getLogger("qtrader.oms.event_store")


class EventStore:
    """Persistent storage for all system events.
    
    This is the foundation for deterministic replay and state reconstruction.
    State(t) = Σ Events[0 → t]
    """

    def __init__(self, log_path: str = "data/events/event_log.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = None

    async def start(self) -> None:
        """Open the event log file for appending."""
        self._file = open(self.log_path, mode="a", encoding="utf-8")
        _LOG.info(f"EVENT_STORE | Started logging to {self.log_path}")

    async def stop(self) -> None:
        """Close the event log file."""
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            _LOG.info("EVENT_STORE | Stopped logging")

    def connect_bus(self, event_bus: EventBusProtocol) -> None:
        """Subscribe to all event types for centralized logging."""
        for event_type in EventType:
            event_bus.subscribe(event_type, self.record_event)

    def record_event(self, data: Any) -> None:
        """Record an event to the persistent log in JSONL format."""
        if not self._file:
            return

        try:
            # We assume 'data' is a dataclass or dict. 
            # If it's a dataclass, we convert to dict.
            if hasattr(data, "__dict__"):
                event_dict = self._serialize_event(data)
            else:
                event_dict = data

            # Add timestamp if missing (though events usually have it)
            if "timestamp" not in event_dict:
                 event_dict["timestamp"] = datetime.utcnow().isoformat()

            # Write as JSON line
            self._file.write(json.dumps(event_dict) + "\n")
            # In HFT we might not flush every line for performance, 
            # but for reliability we might do it periodically.
        except Exception as e:
            _LOG.error(f"EVENT_STORE | Failed to record event: {e}")

    def _serialize_event(self, event: Any) -> dict[str, Any]:
        """Convert event dataclass to serializable dict."""
        from dataclasses import asdict, is_dataclass
        from decimal import Decimal
        from enum import Enum

        def custom_serializer(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, Enum):
                return obj.name
            if is_dataclass(obj):
                return asdict(obj)
            if isinstance(obj, (set, tuple)):
                return list(obj)
            return str(obj)

        if is_dataclass(event):
            # asdict is deep, but might need custom handling for Decimal/datetime
            # So we do a shallow dict and then clean up or use a better serializer.
            # Using asdict with a factory or just manual cleanup:
            d = asdict(event)
            # Recursively fix types for JSON
            return self._json_ready(d, custom_serializer)
        return {"data": str(event)}

    def _json_ready(self, data: Any, serializer: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._json_ready(v, serializer) for k, v in data.items()}
        if isinstance(data, list):
            return [self._json_ready(v, serializer) for v in data]
        if isinstance(data, (datetime, Decimal, Enum)):
            return serializer(data)
        return data
