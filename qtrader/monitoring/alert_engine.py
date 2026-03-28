from __future__ import annotations

import collections
import time
from typing import Any, Dict, List, Mapping, Optional

from loguru import logger

from qtrader.monitoring.metrics_collector import MetricsCollector


class AlertEngine:
    """
    Sovereign Authority for Multi-Channel Alerting.
    Monitors system telemetry snapshots for budget and risk breaches.
    Triggers immediate human or automated incident response.
    """

    _instance: Optional[AlertEngine] = None

    def __init__(self, rules_policy: Mapping[str, Any]) -> None:
        self.rules = rules_policy.get("rules", {})
        self.channels = rules_policy.get("channels", {})
        self._metrics_collector = MetricsCollector.get_instance()
        self._alert_history: Dict[str, float] = {}
        self._cooldown_sec = 60.0 # Prevent alert fatigue

    @classmethod
    def get_instance(cls, rules_policy: Optional[dict[str, Any]] = None) -> AlertEngine:
        if cls._instance is None:
             if rules_policy is None:
                  # Prototype fallback
                  rules_policy = {"rules": {}}
             cls._instance = AlertEngine(rules_policy)
        return cls._instance

    def check_alerts(self) -> List[str]:
        """
        Scan current metrics snapshot against threshold rules.
        Returns: list of triggered alert names.
        """
        # 1. Capture current telemetry snapshot
        report = self._metrics_collector.flush_report()
        triggered = []

        for name, rule in self.rules.items():
            metric_name = rule.get("metric")
            threshold = rule.get("threshold")
            stat_key = rule.get("stat", "value")
            
            # Retrieve actual value from the composite report
            actual = self._get_metric_value(report, metric_name, stat_key)
            if actual is None:
                 continue
                 
            if actual > threshold:
                 # Check notification cooldown
                 if self._should_notify(name):
                      triggered.append(name)
                      self._dispatch_alert(name, actual, rule)
        
        return triggered

    def _get_metric_value(self, report: dict[str, Any], metric: str, stat: str) -> Optional[float]:
        """Heuristically navigate the nested metrics report."""
        if stat == "value":
             # Counters or Gauges
             return report["counters"].get(metric) or report["gauges"].get(metric)
        
        # Summaries (avg, p99, etc)
        summary = report["summaries"].get(metric)
        if summary:
             return summary.get(stat)
        
        return None

    def _should_notify(self, rule_name: str) -> bool:
        """Prevent spamming multiple alerts for the same breach."""
        last_alert = self._alert_history.get(rule_name, 0)
        if time.perf_counter() - last_alert > self._cooldown_sec:
             self._alert_history[rule_name] = time.perf_counter()
             return True
        return False

    def _dispatch_alert(self, name: str, actual: float, rule: dict[str, Any]) -> None:
        """Coordinate multi-channel incident response."""
        severity = rule.get("severity", "WARNING")
        limit = rule.get("threshold")
        action = rule.get("action")
        
        msg = (
            f"ALERT [{severity}] Breach='{name}': Actual={actual:.3f} (Limit={limit}). "
            f"ActionRequired='{action}'"
        )
        
        # 1. Log as Critical/Warning
        if severity == "CRITICAL":
             logger.critical(f"[ALERT-CORE] {msg}")
             # 2. (Planned) Trigger FailFastEngine halt
        else:
             logger.warning(f"[ALERT-CORE] {msg}")

        # 3. MOCK: Dispatches to Telegram/Email
        if self.channels.get("telegram", {}).get("enabled"):
             # Simulating Telegram send
             logger.info(f"[TELEGRAM] PUSH -> {msg}")
             
        if self.channels.get("email", {}).get("enabled"):
             # Simulating Email send
             logger.info(f"[EMAIL] SEND -> {msg}")


# Global singleton authority
alert_engine = AlertEngine.get_instance()
