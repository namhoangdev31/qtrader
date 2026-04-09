from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from qtrader.core.metrics import metrics


class AlertEngine:
    def __init__(
        self,
        rules_path: str = "qtrader/alerts/alert_rules.json",
        incident_log_path: str = "qtrader/alerts/incident_log.json",
    ) -> None:
        self.rules_path = rules_path
        self.incident_log_path = incident_log_path
        self.rules = self._load_rules()
        self._lock = asyncio.Lock()
        self._ensure_incident_log()

    def _load_rules(self) -> dict[str, Any]:
        if not os.path.exists(self.rules_path):
            logger.warning(
                f"ALERT_ENGINE | Rules file not found: {self.rules_path}. Using defaults."
            )
            return {"rules": {}, "channels": {}}
        with open(self.rules_path) as f:
            return json.load(f)

    def _ensure_incident_log(self) -> None:
        if not os.path.exists(self.incident_log_path):
            with open(self.incident_log_path, "w") as f:
                json.dump([], f)

    async def check_metrics(self) -> list[dict[str, Any]]:
        snapshot = await metrics.snapshot()
        triggered_alerts = []
        for name, rule in self.rules.get("rules", {}).items():
            metric_name = rule.get("metric")
            threshold = rule.get("threshold")
            operator = rule.get("operator", ">")
            actual_value = self._get_metric_value(snapshot, metric_name, rule.get("stat"))
            if actual_value is None:
                continue
            if self._evaluate_rule(actual_value, threshold, operator):
                alert_info = {
                    "rule": name,
                    "metric": metric_name,
                    "actual": float(actual_value),
                    "threshold": threshold,
                    "severity": rule.get("severity", "WARNING"),
                    "action": rule.get("action", "LOG_INCIDENT"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                triggered_alerts.append(alert_info)
                await self.trigger(alert_info)
        return triggered_alerts

    def _get_metric_value(
        self, snapshot: dict[str, Any], metric_name: str, stat: str | None
    ) -> float | None:
        if metric_name in snapshot.get("counters", {}):
            return float(snapshot["counters"][metric_name])
        histogram = snapshot.get("histograms", {}).get(metric_name)
        if histogram:
            stat_key = stat or "avg"
            return float(histogram.get(stat_key, 0.0))
        return None

    def _evaluate_rule(self, actual: float, threshold: float, operator: str) -> bool:
        if operator == ">":
            return actual > threshold
        if operator == "<":
            return actual < threshold
        if operator == ">=":
            return actual >= threshold
        if operator == "<=":
            return actual <= threshold
        if operator == "==":
            return actual == threshold
        return False

    async def trigger(self, alert_info: dict[str, Any]) -> None:
        severity = alert_info.get("severity", "WARNING")
        msg = f"ALERT_{severity} | {alert_info['rule']} | {alert_info['metric']}={alert_info['actual']} (Threshold: {alert_info['threshold']})"
        if severity == "CRITICAL":
            logger.critical(msg)
        else:
            logger.warning(msg)
        async with self._lock:
            await self._log_incident(alert_info)

    async def _log_incident(self, alert_info: dict[str, Any]) -> None:
        try:
            with open(self.incident_log_path) as f:
                incidents = json.load(f)
            incidents.append(alert_info)
            if len(incidents) > 1000:
                incidents = incidents[-1000:]
            with open(self.incident_log_path, "w") as f:
                json.dump(incidents, f, indent=2)
        except Exception as e:
            logger.error(f"ALERT_ENGINE_LOG_FAILURE | {e}")


alert_engine = AlertEngine()
