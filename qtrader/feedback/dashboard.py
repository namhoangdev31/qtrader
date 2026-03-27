from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.feedback.dashboard")


class LiveGovernanceDashboard:
    """
    Principal Real-Time Monitoring Dashboard System.

    Objective: Provide sub-second visibility into the platform's state (performance,
    risk, and execution health) for operators and institutional stakeholders.

    Model: Reactive State Aggregation (PnL, NAV, DD, Risk, Allocation, Execution).
    Constraint: Update frequency <= 1s.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional governance dashboard.
        """
        # Telemetry for institutional situational awareness.
        self._total_dashboard_refreshes: int = 0
        self._active_governance_alerts: list[str] = []
        self._last_refresh_timestamp: float = 0.0

    def update_dashboard_state(
        self,
        performance: dict[str, Any],
        risk: dict[str, Any],
        execution: dict[str, Any],
        allocation: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Produce a terminal dashboard state and check for operational alerts.

        Forensic Logic:
        1. Freshness Gating: Rejects updates older than the 1s threshold.
        2. Metric Aggregation: Unifies PnL, NAV, Drawdown, Risk Score, and Fill Rate.
        3. Alert Governance: Triggers immediate logging for risk or execution breaches.
        """
        refresh_start = time.time()

        # 1. Freshness Validation (Protects against legacy state artifacts).
        data_ts = float(performance.get("timestamp", refresh_start))
        if (refresh_start - data_ts) > 1.0:
            stale_lat = refresh_start - data_ts
            _LOG.warning(f"[DASHBOARD] STALE_DATA_REJECTED | Latency: {stale_lat:.2f}s")
            return {
                "status": "STALE_DATA_ARTIFACT",
                "details": "Dashboard update rejected due to sub-second freshness timeout.",
            }

        # 2. Metric Aggregation.
        pnl = float(performance.get("pnl", 0.0))
        nav = float(performance.get("nav", 0.0))
        drawdown = float(risk.get("drawdown", 0.0))
        risk_score = float(risk.get("risk_score", 0.0))
        fill_rate = float(execution.get("fill_rate", 1.0))

        # 3. Alert Processing (Operational Breach detection).
        new_alerts = []
        stress_threshold = 0.8
        fill_threshold = 0.5
        drawdown_threshold = 0.1

        if risk_score > stress_threshold:
            new_alerts.append(f"RISK_CRITICAL: {risk_score:.2f}")
        if fill_rate < fill_threshold:
            new_alerts.append(f"EXECUTION_FAILURE: {fill_rate:.2%}")
        if drawdown > drawdown_threshold:
            new_alerts.append(f"DRAWDOWN_BREACH: {drawdown:.2%}")

        self._active_governance_alerts = new_alerts
        self._last_refresh_timestamp = refresh_start
        self._total_dashboard_refreshes += 1

        if self._active_governance_alerts:
            alert_summary = ", ".join(self._active_governance_alerts)
            _LOG.error(f"[DASHBOARD] OPERATIONAL_BREACH | {alert_summary}")
        else:
            _LOG.info(f"[DASHBOARD] STATE_SYNCED | NAV: {nav:,.2f} | Risk: {risk_score:.2f}")

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "DASHBOARD_SYNCHRONIZED",
            "metrics": {
                "live_pnl": round(pnl, 4),
                "current_nav": round(nav, 4),
                "current_drawdown": round(drawdown, 4),
                "system_risk_score": round(risk_score, 4),
            },
            "execution": {
                "fill_rate": round(fill_rate, 4),
                "avg_slippage": round(float(execution.get("slippage", 0.0)), 4),
            },
            "governance_status": {
                "active_alerts": list(self._active_governance_alerts),
                "operating_regime": "NORMAL" if not self._active_governance_alerts else "CRITICAL",
                "strategy_allocation_pct": allocation.get("distribution_pct", {}),
            },
            "forensics": {
                "refresh_latency_ms": round((time.time() - refresh_start) * 1000, 4),
                "data_freshness_sec": round(refresh_start - data_ts, 4),
            },
        }

        return artifact

    def get_dashboard_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional dashboard health.
        """
        return {
            "status": "GOVERNANCE_TELEMETRY",
            "total_refresh_cycles": self._total_dashboard_refreshes,
            "active_alert_count": len(self._active_governance_alerts),
            "heartbeat_timestamp": self._last_refresh_timestamp,
        }
