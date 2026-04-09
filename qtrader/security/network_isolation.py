from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Final

_LOG = logging.getLogger("qtrader.security.network_isolation")


class NetworkZone(Enum):
    PUBLIC = auto()
    RESEARCH = auto()
    TRADING = auto()
    RISK = auto()
    COMPLIANCE = auto()


class NetworkIsolationEnforcer:
    _POLICY: Final[dict[NetworkZone, frozenset[NetworkZone]]] = {
        NetworkZone.TRADING: frozenset([NetworkZone.RISK, NetworkZone.COMPLIANCE]),
        NetworkZone.RISK: frozenset([NetworkZone.TRADING, NetworkZone.COMPLIANCE]),
        NetworkZone.RESEARCH: frozenset([NetworkZone.COMPLIANCE]),
        NetworkZone.COMPLIANCE: frozenset(),
        NetworkZone.PUBLIC: frozenset(),
    }

    def __init__(self) -> None:
        self._stats = {"denied": 0, "allowed": 0}

    def check_access(self, src: NetworkZone, dst: NetworkZone) -> bool:
        allowed_destinations = self._POLICY.get(src, frozenset())
        if dst in allowed_destinations:
            self._stats["allowed"] += 1
            _LOG.info(f"[NETWORK_CHECK] ALLOW | Source: {src.name} | Destination: {dst.name}")
            return True
        self._stats["denied"] += 1
        _LOG.warning(f"[NETWORK_CHECK] DENY | Source: {src.name} | Destination: {dst.name}")
        return False

    def get_report(self) -> dict[str, Any]:
        total = self._stats["allowed"] + self._stats["denied"]
        return {
            "status": "REPORT",
            "cross_zone_traffic": total,
            "denied_connections": self._stats["denied"],
            "violation_rate": round(self._stats["denied"] / total, 4) if total > 0 else 0.0,
        }
