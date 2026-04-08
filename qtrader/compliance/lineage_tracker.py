from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.compliance.lineage_tracker")


@dataclass(slots=True)
class LineageRecord:
    """
    Industrial execution chain representation.
    Tracks every stage from Alpha Signal to terminal Position state.
    """

    signal_id: str | None = None
    decision_id: str | None = None
    order_id: str | None = None
    fill_id: str | None = None
    position_id: str | None = None


class LineageTracker:
    """
    Principal Trade Lineage System.

    Objective: Maintain granular, bi-directional traceability for every trade.
    Enables forensic audit reconstruction (Fill -> Signal) and impact analysis.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional traceability registry.
        """
        # Bi-directional ID Registry: Maps ANY ID in a chain to its LineageRecord.
        self._registry: dict[str, LineageRecord] = {}

        # Telemetry for institutional situational awareness.
        self._stats = {"total_tracked_chains": 0, "verified_complete_chains": 0}

    def link(self, **kwargs: str) -> None:
        """
        Atomically link lifecycle stage identifiers.

        Usage:
            tracker.link(signal_id="S1", decision_id="D1")
            tracker.link(decision_id="D1", order_id="O1")

        The system automatically merges links into a unified LineageRecord.
        """
        # 1. Quaternary Resolution: Find if any ID belongs to an existing chain.
        record = None
        for val in kwargs.values():
            if val in self._registry:
                record = self._registry[val]
                break

        # 2. Initialization: Create new chain if no existing map found.
        if not record:
            record = LineageRecord()
            self._stats["total_tracked_chains"] += 1

        # 3. Aggregation: Update record and bi-directional map.
        for key, val in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, val)
                self._registry[val] = record

        _LOG.info(f"[LINEAGE] LINK_ESTABLISHED | {kwargs}")

    def get_forensics(self, any_id: str) -> dict[str, str | None]:
        """
        Reconstruct the full execution forensic chain for a given identifier.
        Enables bi-directional trace (e.g., Fill_ID -> Signal_ID).
        """
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
        """
        Verify if an execution chain has reached full traceability.
        Checked against: Signal, Decision, Order, Fill, Position.
        """
        chain = self.get_forensics(any_id)
        is_full = all(v is not None for v in chain.values())

        if is_full:
            self._stats["verified_complete_chains"] += 1

        return is_full

    def get_report(self) -> dict[str, Any]:
        """
        Industrial situational awareness report for trade lineage fidelity.
        """
        return {
            "status": "LINEAGE",
            "total_chains": self._stats["total_tracked_chains"],
            "complete_chains": self._stats["verified_complete_chains"],
        }
