from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, cast

_LOG = logging.getLogger("qtrader.audit.dashboard")


class UserRole(Enum):
    """
    Institutional User Roles for Governance Visibility.
    Governs the perspective and data density presented in the dashboard for compliance.
    """

    TRADER = auto()
    RISK_MANAGER = auto()
    AUDITOR = auto()


class GovernanceDashboard:
    """
    Principal Governance Visualization System.

    Objective: Provide high-fidelity, real-time visibility into platform performance,
    risk metrics, and compliance violations through role-based perspectives.

    Model: Role-Based Filtering with Sub-Second Synchronization.
    Latency Constraint: < 1.0s Refresh Target.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional visibility controller.
        """
        # Telemetry for institutional operational monitoring.
        self._stats = {"access_events": 0, "last_latency_ms": 0.0}

    def render_view(
        self,
        role: UserRole,
        performance_metrics: dict[str, Any],
        risk_metrics: dict[str, Any],
        active_violations: list[dict[str, Any]],
        system_state: str,
    ) -> dict[str, Any]:
        """
        Produce a real-time structural governance view tailored to the user's role.

        Forensic Logic:
        1. Access Authorization Log: All dashboard refreshes are logged for audit.
        2. Perspective Filtering: Redacts sensitive forensic fields for TRADER roles.
        3. Synchronization: Aligns UI view with terminal risk and performance state.
        """
        start_time = time.time()

        # 1. Forensic Access Accounting.
        _LOG.info(f"[DASHBOARD] ACCESS_REFRESH | Role: {role.name}")
        self._stats["access_events"] += 1

        # 2. Role-Based Data Redaction / Perspective Filtering.
        # Auditors see the full evidence chain; Traders see only alert presence.
        filtered_alerts = active_violations
        if role == UserRole.TRADER:
            # Hide industrial forensic IDs and severity codes for trader focus.
            filtered_alerts = [
                {
                    "type": alert.get("type", "UNKNOWN"),
                    "timestamp": alert.get("timestamp", 0.0),
                }
                for alert in active_violations
            ]

        # 3. Institutional View Artifact construction.
        view = {
            "status": "DASHBOARD_LIVE",
            "role": role.name,
            "platform_state": system_state,
            "telemetry": {
                "performance": {
                    "Total_PnL": performance_metrics.get("pnl", 0.0),
                    "Core_Equity": performance_metrics.get("equity", 0.0),
                },
                "risk": {
                    "VaR_Terminal": risk_metrics.get("VaR", 0.0),
                    "Max_Drawdown": risk_metrics.get("MaxDD", 0.0),
                },
                "alerts": filtered_alerts[:10],  # Sub-second visibility sample.
            },
            "timestamp": time.time(),
            "refresh_latency_ms": round((time.time() - start_time) * 1000, 4),
        }

        self._stats["last_latency_ms"] = cast("float", view["refresh_latency_ms"])

        return view

    def get_visibility_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional dashboard performance.
        """
        return {
            "status": "VISIBILITY",
            "access_count": self._stats["access_events"],
            "last_latency_ms": self._stats["last_latency_ms"],
        }
