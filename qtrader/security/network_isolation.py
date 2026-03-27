from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Final

_LOG = logging.getLogger("qtrader.security.network_isolation")


class NetworkZone(Enum):
    """
    Zero-Trust Infrastructure Zones.
    """

    PUBLIC = auto()  # External APIs (Binance, Bloomberg)
    RESEARCH = auto()  # Model Training / Alpha Discovery
    TRADING = auto()  # Execution Engine / Order Management
    RISK = auto()  # Risk Firewall / Pre-trade validation
    COMPLIANCE = auto()  # Audit Trail / Event Storage


class NetworkIsolationEnforcer:
    """
    Principal Network Security Engine.

    Objective: Segment system components into cryptographically isolated zones.
    Enforces a strict 'Deny-by-Default' policy and programmatically blocks
    unauthorized cross-zone navigation according to the KILO.AI Industrial Protocol.
    """

    # Immutable Whitelist Policy Matrix Baseline.
    # Rule: Path(src -> dst)
    _POLICY: Final[dict[NetworkZone, frozenset[NetworkZone]]] = {
        NetworkZone.TRADING: frozenset([NetworkZone.RISK, NetworkZone.COMPLIANCE]),
        NetworkZone.RISK: frozenset([NetworkZone.TRADING, NetworkZone.COMPLIANCE]),
        NetworkZone.RESEARCH: frozenset([NetworkZone.COMPLIANCE]),
        NetworkZone.COMPLIANCE: frozenset(),  # Compliance is a storage sink only.
        NetworkZone.PUBLIC: frozenset(),  # Public cannot push into internal zones.
    }

    def __init__(self) -> None:
        """
        Initialize the structural network enforcer.
        """
        # Internal situational awareness counters.
        self._stats = {"denied": 0, "allowed": 0}

    def check_access(self, src: NetworkZone, dst: NetworkZone) -> bool:
        """
        Terminal Authorization Logic.

        Rule: Access is ONLY granted if explicitly defined in the policy whitelist.
        Zero lateral movement is allowed beyond authorized paths.

        Returns:
            bool: True (ALLOW) or False (DENY).
        """
        allowed_destinations = self._POLICY.get(src, frozenset())

        if dst in allowed_destinations:
            self._stats["allowed"] += 1
            _LOG.info(f"[NETWORK_CHECK] ALLOW | Source: {src.name} | Destination: {dst.name}")
            return True

        self._stats["denied"] += 1
        _LOG.warning(f"[NETWORK_CHECK] DENY | Source: {src.name} | Destination: {dst.name}")
        return False

    def get_report(self) -> dict[str, Any]:
        """
        Generate network security situational awareness report.
        """
        total = self._stats["allowed"] + self._stats["denied"]
        return {
            "status": "REPORT",
            "cross_zone_traffic": total,
            "denied_connections": self._stats["denied"],
            "violation_rate": (round(self._stats["denied"] / total, 4) if total > 0 else 0.0),
        }
