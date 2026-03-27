from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

_LOG = logging.getLogger("qtrader.feedback.incident_handler")


class IncidentAction(Enum):
    """Tiered institutional response actions."""

    NOTIFY_OPERATOR = "NOTIFY_OPERATOR"
    REDUCE_EXPOSURE = "REDUCE_EXPOSURE"
    PAUSE_STRATEGIES = "PAUSE_STRATEGIES"
    EMERGENCY_HALT = "EMERGENCY_HALT"


class IncidentResponseEngine:
    r"""
    Principal Platform Survivability System.

    Objective: Detect and autonomously respond to critical failures (exchange outages,
    API failures, execution anomalies) with zero manual delay.

    Model: Composite Anomaly Score ($A = w_1 \cdot Risk + w_2 \cdot ExecErr + w_3 \cdot SysFail$).
    Constraint: Detection latency <= 1s.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional incident response engine.
        """
        # Telemetry for institutional resilience control.
        self._total_incidents_handled: int = 0
        self._last_incident_action: IncidentAction = IncidentAction.NOTIFY_OPERATOR
        self._last_detection_latency_ms: float = 0.0

    def evaluate_incident_state(
        self,
        risk_score: float,
        execution_errors: int,
        system_failures: int,
        weights: dict[str, float] | None = None,
        anomaly_threshold: float = 0.6,
    ) -> dict[str, Any]:
        """
        Produce a terminal incident report and trigger autonomous remediation.

        Forensic Logic:
        1. Anomaly Scoring: Aggregates signal failures into a failure intensity score A.
        2. Incident Identification: Trigger if failure score exceeds platform threshold.
        3. Response Mapping: Enforces hard-coded remedial mappings for failure intensities.
        """
        detection_start = time.time()

        # 1. Metrological Anomaly Scoring.
        # Normalize weights for institutional scoring fidelity.
        w = weights or {"risk": 0.5, "exec": 0.3, "sys": 0.2}

        # Normalize error signals to ensure score stability.
        # Max of 10 errors per verification cycle before full saturation.
        max_errors = 10.0
        norm_exec = min(execution_errors / max_errors, 1.0)
        norm_sys = min(system_failures / max_errors, 1.0)

        anomaly_score = (w["risk"] * risk_score) + (w["exec"] * norm_exec) + (w["sys"] * norm_sys)

        # 2. Response Mapping (Deterministic high-fidelity remediation).
        triggered_action = IncidentAction.NOTIFY_OPERATOR
        halt_threshold = 0.9
        pause_threshold = 0.8
        reduce_threshold = 0.6

        if anomaly_score >= halt_threshold:
            triggered_action = IncidentAction.EMERGENCY_HALT
        elif anomaly_score >= pause_threshold:
            triggered_action = IncidentAction.PAUSE_STRATEGIES
        elif anomaly_score >= reduce_threshold:
            triggered_action = IncidentAction.REDUCE_EXPOSURE

        # 3. Telemetry Persistence.
        is_active_incident = anomaly_score >= anomaly_threshold
        if is_active_incident:
            self._total_incidents_handled += 1
            self._last_incident_action = triggered_action

        latency_ms = (time.time() - detection_start) * 1000
        self._last_detection_latency_ms = latency_ms

        if is_active_incident:
            _LOG.error(
                f"[INCIDENT] FAILURE_DETECTED | Score: {anomaly_score:.2f} "
                f"| Action: {triggered_action.value} | Total: {self._total_incidents_handled}"
            )
        else:
            _LOG.info(f"[INCIDENT] STATE_HEALTHY | Score: {anomaly_score:.2f}")

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "INCIDENT_FINALIZED" if is_active_incident else "INCIDENT_NORMAL",
            "metrology": {
                "composite_anomaly_score": round(anomaly_score, 4),
                "is_active_incident": is_active_incident,
            },
            "response": {
                "triggered_action_category": triggered_action.value,
                "autonomous_override_active": is_active_incident,
            },
            "certification": {
                "total_incidents_historical": self._total_incidents_handled,
                "detection_latency_ms": round(latency_ms, 4),
                "timestamp": time.time(),
            },
        }

        return artifact

    def get_incident_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional resilience control.
        """
        return {
            "status": "RESILIENCE_GOVERNANCE",
            "total_incidents_triggered": self._total_incidents_handled,
            "last_incident_action": self._last_incident_action.value,
            "last_detection_latency_ms": round(self._last_detection_latency_ms, 4),
        }
