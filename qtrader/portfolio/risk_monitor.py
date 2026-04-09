from __future__ import annotations
import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.risk_monitor")


class RealTimeRiskMonitor:
    def __init__(
        self,
        var_weight: float = 0.3,
        dd_weight: float = 0.5,
        exp_weight: float = 0.2,
        risk_limit: float = 1.0,
    ) -> None:
        self._w1 = var_weight
        self._w2 = dd_weight
        self._w3 = exp_weight
        self._limit = risk_limit
        self._cumulative_alert_count: int = 0
        self._historical_peak_risk_score: float = 0.0

    def evaluate_live_risk(self, live_data: dict[str, Any]) -> dict[str, Any]:
        start_time = time.time()
        var_val = float(live_data.get("var", 0.0))
        dd_val = float(live_data.get("drawdown", 0.0))
        exp_val = float(live_data.get("exposure", 0.0))
        aggregated_risk_score = self._w1 * var_val + self._w2 * dd_val + self._w3 * exp_val
        risk_level = "NORMAL"
        is_alert_active = False
        if aggregated_risk_score >= self._limit:
            risk_level = "CRITICAL"
            is_alert_active = True
            self._cumulative_alert_count += 1
        elif aggregated_risk_score >= 0.8 * self._limit:
            risk_level = "WARNING"
        elif aggregated_risk_score >= 0.5 * self._limit:
            risk_level = "ELEVATED"
        self._historical_peak_risk_score = max(
            self._historical_peak_risk_score, aggregated_risk_score
        )
        if is_alert_active:
            _LOG.error(
                f"[RISK] ALERT_TRIGGERED | Level: {risk_level} | Score: {aggregated_risk_score:.4f} | Limit: {self._limit}"
            )
        else:
            _LOG.info(
                f"[RISK] STATE_CHECK | Level: {risk_level} | Score: {aggregated_risk_score:.4f}"
            )
        artifact = {
            "status": "RISK_MONITORED",
            "result": "PASS" if not is_alert_active else "ALERT",
            "level": risk_level,
            "metrics": {
                "risk_score_aggregated": round(aggregated_risk_score, 4),
                "cumulative_alert_count": self._cumulative_alert_count,
            },
            "factor_trace": {
                "var_contribution": round(self._w1 * var_val, 4),
                "drawdown_contribution": round(self._w2 * dd_val, 4),
                "exposure_contribution": round(self._w3 * exp_val, 4),
            },
            "certification": {
                "institutional_risk_limit": self._limit,
                "peak_risk_observed": round(self._historical_peak_risk_score, 4),
                "timestamp": time.time(),
                "compute_latency_ms": round((time.time() - start_time) * 1000, 4),
            },
        }
        return artifact

    def get_risk_telemetry(self) -> dict[str, Any]:
        return {
            "status": "RISK_GOVERNANCE",
            "total_alerts_lifecycle": self._cumulative_alert_count,
            "historical_peak_score": round(self._historical_peak_risk_score, 4),
            "monitoring_veracity": "ACTIVE (Sub-1s Gating)",
        }
