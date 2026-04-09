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
    def __init__(self, log_path: str = "data/events/order_event_log.jsonl") -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._rust_store = RustEventStore(log_path)
        self._log = logging.getLogger("qtrader.oms.event_store")

    async def record_event(self, event: Any) -> None:
        try:
            event_dict = self._serialize(event)
            event_dict["timestamp"] = datetime.utcnow().isoformat()
            json_payload = json.dumps(event_dict)
            self._rust_store.record_event(json_payload)
        except Exception as e:
            self._log.exception("Persistent event logging failed", exc_info=e)

    def replay_order(self, order_id: str) -> list[dict[str, Any]]:
        if not os.path.exists(self.log_path):
            return []
        trace = []
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                target_id = ev.get("order_id") or (ev.get("order") or {}).get("order_id")
                if target_id == order_id:
                    trace.append(ev)
        return trace

    def get_last_sequence(self, symbol: str) -> int:
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
        if not os.path.exists(self.log_path):
            return []
        prices = []
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
                    and (venue != exclude_venue)
                ):
                    data = ev.get("data", {})
                    price = data.get("last_price") or data.get("c") or 0.0
                    if price > 0:
                        latest_price = float(price)
        return latest_price

    def get_deltas(self, symbol: str, start_seq: int) -> list[dict[str, Any]]:
        if not os.path.exists(self.log_path):
            return []
        deltas = []
        with open(self.log_path) as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("symbol") == symbol and ev.get("seq_id", 0) >= start_seq:
                    deltas.append(ev)
        deltas.sort(key=lambda x: x.get("seq_id", 0))
        return deltas

    def _serialize(self, obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return self._serialize(obj.model_dump())
        if is_dataclass(obj):
            return {k: self._serialize(v) for (k, v) in asdict(obj).items()}
        if isinstance(obj, dict):
            return {k: self._serialize(v) for (k, v) in obj.items()}
        if isinstance(obj, list):
            return [self._serialize(v) for v in obj]
        res = obj
        if isinstance(obj, Decimal):
            res = float(obj)
        elif isinstance(obj, Enum):
            res = obj.name
        elif isinstance(obj, datetime):
            res = obj.isoformat()
        else:
            try:
                json.dumps(obj)
            except (TypeError, OverflowError):
                res = str(obj)
        return res
