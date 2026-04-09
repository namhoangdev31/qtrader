from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.compliance.lineage_tracker")


@dataclass(slots=True)
class LineageRecord:
    signal_id: str | None = None
    decision_id: str | None = None
    order_id: str | None = None
    fill_id: str | None = None
    position_id: str | None = None


class LineageTracker:
    def __init__(self) -> None:
        self._registry: dict[str, LineageRecord] = {}
        self._stats = {"total_tracked_chains": 0, "verified_complete_chains": 0}

    def link(self, **kwargs: str) -> None:
        record = None
        for val in kwargs.values():
            if val in self._registry:
                record = self._registry[val]
                break
        if not record:
            record = LineageRecord()
            self._stats["total_tracked_chains"] += 1
        for key, val in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, val)
                self._registry[val] = record
        _LOG.info(f"[LINEAGE] LINK_ESTABLISHED | {kwargs}")

    def get_forensics(self, any_id: str) -> dict[str, str | None]:
        record = self._registry.get(any_id)
        if not record:
            return {
                "signal_id": None,
                "decision_id": None,
                "order_id": None,
                "fill_id": None,
                "position_id": None,
            }
        return {
            "signal_id": record.signal_id,
            "decision_id": record.decision_id,
            "order_id": record.order_id,
            "fill_id": record.fill_id,
            "position_id": record.position_id,
        }

    def is_complete(self, any_id: str) -> bool:
        chain = self.get_forensics(any_id)
        is_full = all((v is not None for v in chain.values()))
        if is_full:
            self._stats["verified_complete_chains"] += 1
        return is_full

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "LINEAGE",
            "total_chains": self._stats["total_tracked_chains"],
            "complete_chains": self._stats["verified_complete_chains"],
        }
