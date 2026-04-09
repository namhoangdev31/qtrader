import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from qtrader_core import EventStore as RustEventStore


class EventStore:
    """High-fidelity persistence layer for system events.

    Supports the fundamental architectural requirement: State(t) = Σ Events[0 → t].
    Ensures that for every order, the entire trace of transitions is preserved.
    """

    def __init__(self, log_path: str = "data/events/order_event_log.jsonl") -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._rust_store = RustEventStore(log_path)
        self._log = logging.getLogger("qtrader.oms.event_store")

    async def record_event(self, event: Any) -> None:
        """Append a state-changing event to the persistent log via Rust."""
        try:
            event_dict = self._serialize(event)
            event_dict["timestamp"] = datetime.utcnow().isoformat()

            # Delegate I/O to Rust
            json_payload = json.dumps(event_dict)
            self._rust_store.record_event(json_payload)

        except Exception as e:
            self._log.exception("Persistent event logging failed", exc_info=e)

    def replay_order(self, order_id: str) -> list[dict[str, Any]]:
        """Replay events for a specific order to reconstruct its state."""
        if not os.path.exists(self.log_path):
            return []

        trace = []
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                # Some events have 'order_id' at root, some in nested 'order'
                target_id = ev.get("order_id") or (ev.get("order") or {}).get("order_id")
                if target_id == order_id:
                    trace.append(ev)
        return trace

    def get_last_sequence(self, symbol: str) -> int:
        """Get the last processed sequence ID for a symbol from the log."""
        if not os.path.exists(self.log_path):
            return 0

        last_seq = 0
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("symbol") == symbol and "seq_id" in ev:
                    last_seq = max(last_seq, ev["seq_id"])
        return last_seq

    def get_recent_prices(self, symbol: str, window_size: int = 50) -> list[float]:
        """Fetch the most recent prices for a symbol for statistical validation."""
        if not os.path.exists(self.log_path):
            return []

        prices = []
        # In a real system, we'd use a tail-based approach or a cached index.
        # For this implementation, we read backwards or collect all and tail.
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("symbol") == symbol and ev.get("type") == "MARKET_DATA":
                    data = ev.get("data", {})
                    price = data.get("last_price") or data.get("c") or 0.0
                    if price > 0:
                        prices.append(float(price))

        return prices[-window_size:]

    def get_latest_price_cross_exchange(self, symbol: str, exclude_venue: str) -> float | None:
        """Fetch the latest price for a symbol from a different venue."""
        if not os.path.exists(self.log_path):
            return None

        latest_price = None
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                metadata = ev.get("metadata") or {}
                venue = metadata.get("venue") or ev.get("venue")

                if (
                    ev.get("symbol") == symbol
                    and ev.get("type") == "MARKET_DATA"
                    and venue != exclude_venue
                ):
                    data = ev.get("data", {})
                    price = data.get("last_price") or data.get("c") or 0.0
                    if price > 0:
                        latest_price = float(price)
        return latest_price

    def get_deltas(self, symbol: str, start_seq: int) -> list[dict[str, Any]]:
        """Retrieve deltas for a symbol starting from a specific sequence."""
        if not os.path.exists(self.log_path):
            return []

        deltas = []
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("symbol") == symbol and ev.get("seq_id", 0) >= start_seq:
                    deltas.append(ev)

        # Ensure deltas are sorted by sequence ID for deterministic replay
        deltas.sort(key=lambda x: x.get("seq_id", 0))
        return deltas

    def _serialize(self, obj: Any) -> Any:
        """Deep serialization for events with Decimals/Enums/Pydantic."""
        if hasattr(obj, "model_dump"):
            return self._serialize(obj.model_dump())

        if is_dataclass(obj):
            return {k: self._serialize(v) for k, v in asdict(obj).items()}

        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._serialize(v) for v in obj]

        # Combine simple scalar types into a single return path to satisfy Ruff PLR0911
        res = obj
        if isinstance(obj, Decimal):
            res = float(obj)
        elif isinstance(obj, Enum):
            res = obj.name
        elif isinstance(obj, datetime):
            res = obj.isoformat()
        else:
            # Handle UUID or any other type by converting to string if not serializable
            try:
                json.dumps(obj)
            except (TypeError, OverflowError):
                res = str(obj)

        return res
