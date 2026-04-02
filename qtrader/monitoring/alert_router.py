"""Alert Routing System: dispatches critical system events to Telegram, Email, and webhooks.

Subscribes to ERROR and SYSTEM events on the EventBus and fans out notifications
based on severity and alert channel configuration. All I/O is non-blocking.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from qtrader.core.bus import EventBus

from qtrader.core.event import ErrorEvent, EventType, SystemEvent

log = logging.getLogger("qtrader.alert_router")


# ---------------------------------------------------------------------------
# Alert Severity (controls which channels fire)
# ---------------------------------------------------------------------------
class AlertSeverity(Enum):
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


# ---------------------------------------------------------------------------
# Configuration dataclasses (pulled from env / configs)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TelegramConfig:
    """Telegram Bot API credentials."""
    bot_token: str
    chat_id: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class EmailConfig:
    """SMTP credentials for email alerts."""
    smtp_host: str
    smtp_port: int
    sender: str
    recipients: list[str]
    password: str = ""
    use_tls: bool = True
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class WebhookConfig:
    """Generic webhook (Slack, Discord, PagerDuty, etc.)."""
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AlertRouterConfig:
    """Top-level configuration for the alert routing system."""
    telegram: TelegramConfig | None = None
    email: EmailConfig | None = None
    webhook: WebhookConfig | None = None
    min_severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_seconds: float = 60.0  # De-bounce repeated alerts


# ---------------------------------------------------------------------------
# Abstract Channel
# ---------------------------------------------------------------------------
class AlertChannel(ABC):
    """Base class for an outbound alert delivery channel."""

    @abstractmethod
    async def send(self, subject: str, body: str, severity: AlertSeverity) -> bool:
        """Deliver the alert. Returns True on success."""
        ...


# ---------------------------------------------------------------------------
# Telegram Channel
# ---------------------------------------------------------------------------
class TelegramChannel(AlertChannel):
    """Send alerts via Telegram Bot API (non-blocking HTTP)."""

    _API_TMPL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._url = self._API_TMPL.format(token=config.bot_token)

    async def send(self, subject: str, body: str, severity: AlertSeverity) -> bool:
        icon = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "🔴",
            AlertSeverity.CRITICAL: "🚨",
        }.get(severity, "📢")

        text = f"{icon} *{subject}*\n\n{body}\n\n_{datetime.utcnow().isoformat()}Z_"
        payload = {
            "chat_id": self._config.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        log.info("Telegram alert sent: %s", subject)
                        return True
                    log.warning("Telegram API returned %s", resp.status)
                    return False
        except Exception as exc:
            log.error("Telegram send failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Email Channel (async SMTP via smtplib in executor — keeps event loop free)
# ---------------------------------------------------------------------------
class EmailChannel(AlertChannel):
    """Send alerts via SMTP. Offloads blocking I/O to a thread executor."""

    def __init__(self, config: EmailConfig) -> None:
        self._config = config

    async def send(self, subject: str, body: str, severity: AlertSeverity) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._send_sync, subject, body, severity)

    def _send_sync(self, subject: str, body: str, severity: AlertSeverity) -> bool:
        import smtplib
        from email.mime.text import MIMEText

        tag = f"[{severity.name}]"
        msg = MIMEText(f"{body}\n\nTimestamp: {datetime.utcnow().isoformat()}Z", "plain", "utf-8")
        msg["Subject"] = f"{tag} QTrader Alert: {subject}"
        msg["From"] = self._config.sender
        msg["To"] = ", ".join(self._config.recipients)

        try:
            if self._config.use_tls:
                server = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port)

            if self._config.password:
                server.login(self._config.sender, self._config.password)

            server.sendmail(self._config.sender, self._config.recipients, msg.as_string())
            server.quit()
            log.info("Email alert sent to %s: %s", self._config.recipients, subject)
            return True
        except Exception as exc:
            log.error("Email send failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Webhook Channel (Slack / Discord / PagerDuty / custom)
# ---------------------------------------------------------------------------
class WebhookChannel(AlertChannel):
    """Generic JSON POST webhook."""

    def __init__(self, config: WebhookConfig) -> None:
        self._config = config

    async def send(self, subject: str, body: str, severity: AlertSeverity) -> bool:
        payload = {
            "text": f"[{severity.name}] {subject}: {body}",
            "severity": severity.name,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._config.url,
                    json=payload,
                    headers=self._config.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    ok = 200 <= resp.status < 300
                    if ok:
                        log.info("Webhook alert sent: %s", subject)
                    else:
                        log.warning("Webhook returned %s", resp.status)
                    return ok
        except Exception as exc:
            log.error("Webhook send failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Alert Router (orchestrator)
# ---------------------------------------------------------------------------
_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "INFO": AlertSeverity.INFO,
    "WARNING": AlertSeverity.WARNING,
    "ERROR": AlertSeverity.ERROR,
    "CRITICAL": AlertSeverity.CRITICAL,
}


class AlertRouter:
    """
    Central alert dispatcher.
    Subscribes to EventBus ERROR and SYSTEM events and fans out to configured channels.
    """

    def __init__(self, config: AlertRouterConfig, bus: EventBus | None = None) -> None:
        self._config = config
        self._bus = bus
        self._channels: list[AlertChannel] = []
        self._last_alert_ts: dict[str, float] = {}  # subject -> epoch for cooldown

        # Build active channels
        if config.telegram and config.telegram.enabled:
            self._channels.append(TelegramChannel(config.telegram))
        if config.email and config.email.enabled:
            self._channels.append(EmailChannel(config.email))
        if config.webhook and config.webhook.enabled:
            self._channels.append(WebhookChannel(config.webhook))

        # Subscribe to EventBus
        if self._bus:
            self._subscribe()

        log.info(
            "AlertRouter initialized with %d channel(s), min_severity=%s",
            len(self._channels),
            config.min_severity.name,
        )

    def set_bus(self, bus: EventBus) -> None:
        """Late-bind to EventBus."""
        self._bus = bus
        self._subscribe()

    def _subscribe(self) -> None:
        if not self._bus:
            return
        self._bus.subscribe(EventType.ERROR, self._on_error_event)
        self._bus.subscribe(EventType.SYSTEM, self._on_system_event)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    async def _on_error_event(self, event: ErrorEvent) -> None:
        severity = _SEVERITY_MAP.get(event.severity, AlertSeverity.ERROR)
        body_parts = [event.message]
        if event.exception_type:
            body_parts.append(f"Exception: {event.exception_type}")
        if event.stack_trace:
            # Truncate for notifications
            body_parts.append(f"Trace:\n{event.stack_trace[:500]}")
        await self.dispatch(
            subject=f"Error in {event.source}",
            body="\n".join(body_parts),
            severity=severity,
        )

    async def _on_system_event(self, event: SystemEvent) -> None:
        if event.action in ("EMERGENCY_HALT", "KILL_SWITCH"):
            await self.dispatch(
                subject=f"SYSTEM {event.action}",
                body=f"Reason: {event.reason}",
                severity=AlertSeverity.CRITICAL,
            )

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------
    async def dispatch(self, subject: str, body: str, severity: AlertSeverity) -> None:
        """Route an alert to all enabled channels, respecting severity and cooldown."""
        # 1. Severity gate
        if severity.value < self._config.min_severity.value:
            return

        # 2. Cooldown de-bounce
        now = datetime.utcnow().timestamp()
        last = self._last_alert_ts.get(subject, 0.0)
        if now - last < self._config.cooldown_seconds:
            log.debug("Alert '%s' suppressed by cooldown", subject)
            return
        self._last_alert_ts[subject] = now

        # 3. Fan-out to all channels concurrently
        if not self._channels:
            log.warning("No alert channels configured; alert dropped: %s", subject)
            return

        results = await asyncio.gather(
            *(ch.send(subject, body, severity) for ch in self._channels),
            return_exceptions=True,
        )
        successes = sum(1 for r in results if r is True)
        log.info(
            "Alert dispatched: '%s' severity=%s channels=%d/%d",
            subject,
            severity.name,
            successes,
            len(self._channels),
        )
