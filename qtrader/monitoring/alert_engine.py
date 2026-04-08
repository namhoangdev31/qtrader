"""External Alerting Engine — Standash §2.3, §5.4.

Sends alerts to external channels:
- Slack webhook
- Email (SMTP)
- PagerDuty (API)

All alerting is async and non-blocking to avoid impacting the trading pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("qtrader.monitoring.alerting")


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class AlertMessage:
    """A structured alert message."""

    title: str
    message: str
    severity: AlertSeverity
    source: str = "qtrader"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            import time

            self.timestamp = time.time()


class AlertEngine:
    """External Alerting Engine — Standash §2.3, §5.4.

    Sends alerts to external channels without blocking the trading pipeline.
    Supports:
    - Slack webhook
    - Email (SMTP)
    - PagerDuty (API)
    """

    def __init__(
        self,
        slack_webhook_url: str | None = None,
        smtp_config: dict[str, Any] | None = None,
        pagerduty_routing_key: str | None = None,
    ) -> None:
        self._slack_url = slack_webhook_url
        self._smtp_config = smtp_config
        self._pagerduty_key = pagerduty_routing_key
        self._alert_count: int = 0
        self._failed_count: int = 0

    async def send_alert(self, alert: AlertMessage) -> bool:
        """Send an alert to all configured channels (non-blocking)."""
        self._alert_count += 1
        tasks = []

        if self._slack_url:
            tasks.append(self._send_slack(alert))
        if self._smtp_config:
            tasks.append(self._send_email(alert))
        if self._pagerduty_key:
            tasks.append(self._send_pagerduty(alert))

        if not tasks:
            logger.warning(f"[ALERT] No alert channels configured: {alert.title}")
            return False

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = all(not isinstance(r, Exception) for r in results)

        if not success:
            self._failed_count += 1
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"[ALERT] Failed to send alert: {r}")

        return success

    async def _send_slack(self, alert: AlertMessage) -> None:
        """Send alert to Slack via webhook."""
        if not self._slack_url:
            return

        # Color by severity
        colors = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ffaa00",
            AlertSeverity.CRITICAL: "#ff0000",
        }

        payload = {
            "attachments": [
                {
                    "color": colors.get(alert.severity, "#808080"),
                    "title": f"[{alert.severity.value}] {alert.title}",
                    "text": alert.message,
                    "fields": [
                        {"title": "Source", "value": alert.source, "short": True},
                        {"title": "Severity", "value": alert.severity.value, "short": True},
                    ],
                    "footer": "QTrader Alerting",
                    "ts": int(alert.timestamp),
                }
            ]
        }

        # Add metadata as fields
        if alert.metadata:
            for key, value in list(alert.metadata.items())[:5]:
                payload["attachments"][0]["fields"].append(
                    {"title": key, "value": str(value), "short": True}
                )

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._slack_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"Slack webhook returned {resp.status}")
        except ImportError:
            logger.warning("[ALERT] aiohttp not installed — Slack alert skipped")
        except Exception as e:
            logger.error(f"[ALERT] Slack webhook failed: {e}")
            raise

    async def _send_email(self, alert: AlertMessage) -> None:
        """Send alert via email (SMTP)."""
        if not self._smtp_config:
            return

        try:
            import smtplib
            from email.mime.text import MIMEText

            config = self._smtp_config
            msg = MIMEText(
                f"Severity: {alert.severity.value}\n\n{alert.message}\n\n"
                f"Source: {alert.source}\n"
                f"Metadata: {json.dumps(alert.metadata, indent=2)}",
                "plain",
            )
            msg["Subject"] = f"[{alert.severity.value}] {alert.title}"
            msg["From"] = config.get("from", "qtrader@alert.local")
            msg["To"] = config.get("to", "ops@local")

            server = smtplib.SMTP(config.get("host", "localhost"), config.get("port", 587))
            if config.get("use_tls"):
                server.starttls()
            if config.get("username") and config.get("password"):
                server.login(config["username"], config["password"])
            server.sendmail(msg["From"], msg["To"], msg.as_string())
            server.quit()
        except Exception as e:
            logger.error(f"[ALERT] Email alert failed: {e}")
            raise

    async def _send_pagerduty(self, alert: AlertMessage) -> None:
        """Send alert to PagerDuty."""
        if not self._pagerduty_key:
            return

        severity_map = {
            AlertSeverity.INFO: "info",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.CRITICAL: "critical",
        }

        payload = {
            "routing_key": self._pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": f"{alert.title}: {alert.message}",
                "severity": severity_map.get(alert.severity, "warning"),
                "source": alert.source,
                "custom_details": alert.metadata,
            },
        }

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status not in (200, 202):
                        raise RuntimeError(f"PagerDuty returned {resp.status}")
        except ImportError:
            logger.warning("[ALERT] aiohttp not installed — PagerDuty alert skipped")
        except Exception as e:
            logger.error(f"[ALERT] PagerDuty alert failed: {e}")
            raise

    def get_telemetry(self) -> dict[str, Any]:
        """Get alerting telemetry."""
        return {
            "total_alerts": self._alert_count,
            "failed_alerts": self._failed_count,
            "success_rate": (
                (self._alert_count - self._failed_count) / self._alert_count
                if self._alert_count > 0
                else 1.0
            ),
            "channels": {
                "slack": bool(self._slack_url),
                "email": bool(self._smtp_config),
                "pagerduty": bool(self._pagerduty_key),
            },
        }
