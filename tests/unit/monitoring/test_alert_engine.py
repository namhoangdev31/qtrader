"""Tests for monitoring/alert_engine.py — Standash §2.3, §5.4."""

from __future__ import annotations

import pytest

from qtrader.monitoring.alert_engine import AlertEngine, AlertMessage, AlertSeverity


class TestAlertEngine:
    def test_alert_creation(self) -> None:
        alert = AlertMessage(
            title="Test Alert",
            message="This is a test",
            severity=AlertSeverity.WARNING,
            source="test",
        )
        assert alert.title == "Test Alert"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.timestamp > 0

    @pytest.mark.asyncio
    async def test_send_alert_no_channels(self) -> None:
        engine = AlertEngine()
        alert = AlertMessage(
            title="Test",
            message="Test message",
            severity=AlertSeverity.INFO,
        )
        result = await engine.send_alert(alert)
        assert not result  # No channels configured

    @pytest.mark.asyncio
    async def test_telemetry(self) -> None:
        engine = AlertEngine()
        alert = AlertMessage(
            title="Test",
            message="Test message",
            severity=AlertSeverity.INFO,
        )
        result = await engine.send_alert(alert)
        assert not result  # No channels configured
        telemetry = engine.get_telemetry()
        assert telemetry["total_alerts"] == 1
        assert telemetry["success_rate"] == 1.0  # No tasks = vacuously successful
        assert not telemetry["channels"]["slack"]
        assert not telemetry["channels"]["email"]
        assert not telemetry["channels"]["pagerduty"]

    @pytest.mark.asyncio
    async def test_telemetry_with_channels(self) -> None:
        engine = AlertEngine(
            slack_webhook_url="https://hooks.slack.com/test",
            pagerduty_routing_key="test-key",
        )
        telemetry = engine.get_telemetry()
        assert telemetry["channels"]["slack"]
        assert telemetry["channels"]["pagerduty"]
        assert not telemetry["channels"]["email"]

    def test_all_severities(self) -> None:
        for severity in AlertSeverity:
            alert = AlertMessage(
                title=f"Test {severity.value}",
                message="Test",
                severity=severity,
            )
            assert alert.severity == severity
