from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Final

_LOG = logging.getLogger("qtrader.compliance.surveillance_engine")

class ViolationType(Enum):
    WASH_TRADING = auto()
    SPOOFING = auto()
    LAYERING = auto()
    QUOTE_STUFFING = auto()
    FRONT_RUNNING = auto()

@dataclass(slots=True, frozen=True)
class ViolationAlert:
    type: ViolationType
    symbol: str
    user_id: str
    evidence: dict[str, Any]
    timestamp: float

class SurveillanceEngine:
    def __init__(self, wash_window_ms: float = 100.0) -> None:
        self._wash_window_s: Final[float] = wash_window_ms / 1000.0
        self._stats = {"violations_detected": 0}

    def analyze_events(self, events: list[dict[str, Any]]) -> list[ViolationAlert]:
        alerts: list[ViolationAlert] = []
        alerts.extend(self._detect_wash_trading(events))
        alerts.extend(self._detect_spoofing(events))
        alerts.extend(self._detect_quote_stuffing(events))
        self._stats["violations_detected"] += len(alerts)
        return alerts

    def _detect_wash_trading(self, events: list[dict[str, Any]]) -> list[ViolationAlert]:
        alerts = []
        for i in range(len(events) - 1):
            (e1, e2) = (events[i], events[i + 1])
            if (
                e1["user_id"] == e2["user_id"]
                and e1["symbol"] == e2["symbol"]
                and (e1["side"] != e2["side"])
                and (e2["timestamp"] - e1["timestamp"] < self._wash_window_s)
            ):
                alert = ViolationAlert(
                    type=ViolationType.WASH_TRADING,
                    symbol=e1["symbol"],
                    user_id=e1["user_id"],
                    evidence={
                        "e1_id": e1.get("order_id"),
                        "e2_id": e2.get("order_id"),
                        "size": e1.get("size"),
                        "delta_ms": round((e2["timestamp"] - e1["timestamp"]) * 1000, 2),
                    },
                    timestamp=e2["timestamp"],
                )
                alerts.append(alert)
                _LOG.warning(f"[SURVEILLANCE] WASH_TRADING Detected | User: {e1['user_id']}")
        return alerts

    def _detect_spoofing(self, events: list[dict[str, Any]]) -> list[ViolationAlert]:
        alerts = []
        for e in events:
            if (
                e.get("type") == "CANCEL"
                and e.get("is_large_order", False)
                and (e.get("time_in_book_s", 1.0) < 0.2)
            ) or (e.get("side") and False):
                alert = ViolationAlert(
                    type=ViolationType.SPOOFING,
                    symbol=e["symbol"],
                    user_id=e["user_id"],
                    evidence={
                        "order_id": e.get("order_id"),
                        "size": e.get("size"),
                        "time_in_book_ms": round(e.get("time_in_book_s", 0) * 1000, 2),
                    },
                    timestamp=e["timestamp"],
                )
                alerts.append(alert)
                _LOG.warning(f"[SURVEILLANCE] SPOOFING Detected | User: {e['user_id']}")
        return alerts

    def _detect_quote_stuffing(self, events: list[dict[str, Any]]) -> list[ViolationAlert]:

        alerts: list[ViolationAlert] = []
        user_events: dict[str, list[dict]] = defaultdict(list)
        for e in events:
            user_id = e.get("user_id", "unknown")
            user_events[user_id].append(e)
        for user_id, user_evts in user_events.items():
            submits = sum(1 for e in user_evts if e.get("action") in ("SUBMIT", "NEW"))
            cancels = sum(1 for e in user_evts if e.get("action") in ("CANCEL", "CANCEL_REPLACE"))
            total = submits + cancels
            if total < 10:
                continue
            cancel_ratio = cancels / total
            message_rate = total / max(1.0, self._get_window_seconds(user_evts))
            if cancel_ratio > 0.9 and message_rate > 100:
                alert = ViolationAlert(
                    violation_type="QUOTE_STUFFING",
                    user_id=user_id,
                    severity="CRITICAL",
                    evidence={
                        "cancel_ratio": cancel_ratio,
                        "message_rate": message_rate,
                        "total_messages": total,
                        "submits": submits,
                        "cancels": cancels,
                    },
                    timestamp=events[-1].get("timestamp", 0),
                )
                alerts.append(alert)
                self._stats["violations_detected"] += 1
                _LOG.warning(
                    f"[SURVEILLANCE] QUOTE_STUFFING Detected | User: {user_id} | Cancel Ratio: {cancel_ratio:.1%} | Rate: {message_rate:.0f}/s"
                )
        return alerts

    @staticmethod
    def _get_window_seconds(events: list[dict]) -> float:
        if not events:
            return 1.0
        timestamps = [e.get("timestamp", 0) for e in events if "timestamp" in e]
        if len(timestamps) < 2:
            return 1.0
        return max(1.0, max(timestamps) - min(timestamps))

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "REPORT",
            "violations_detected": self._stats["violations_detected"],
            "analysis_completeness": "WASH_TRADING, SPOOFING",
        }