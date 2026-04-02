import pytest

from qtrader.risk.kill_switch import GlobalKillSwitch


@pytest.fixture
def kill_switch() -> GlobalKillSwitch:
    """Initialize a GlobalKillSwitch for institutional capital certification."""
    return GlobalKillSwitch(dd_limit=0.15, loss_limit=500_000.0, anomaly_limit=0.9)


def test_kill_drawdown_veracity(kill_switch: GlobalKillSwitch) -> None:
    """Verify shutdown on critical drawdown breach (15% limit)."""
    # Scenario: Drawdown 0.20 (20%). Breach.
    report = kill_switch.evaluate_kill_system(
        current_drawdown=0.20,
        current_absolute_loss=0,
        current_anomaly_score=0,
    )

    assert report["status"] == "KILL_SWITCH_ACTIVE"
    assert "CRITICAL_DRAWDOWN_BREACH" in report["state"]["kill_reason"]
    assert report["state"]["is_halted"] is True


def test_kill_capital_loss_precision(kill_switch: GlobalKillSwitch) -> None:
    """Verify shutdown on absolute capital loss breach (500k limit)."""
    # Scenario: Loss 600,000. Breach.
    report = kill_switch.evaluate_kill_system(
        current_drawdown=0,
        current_absolute_loss=600_000,
        current_anomaly_score=0,
    )

    assert report["status"] == "KILL_SWITCH_ACTIVE"
    assert "MAX_LOSS_EXCEEDED" in report["state"]["kill_reason"]


def test_kill_anomaly_intensity_trigger(kill_switch: GlobalKillSwitch) -> None:
    """Verify shutdown on severe anomaly intensity breach (0.9 limit)."""
    # Scenario: Anomaly 0.95. Breach.
    report = kill_switch.evaluate_kill_system(
        current_drawdown=0,
        current_absolute_loss=0,
        current_anomaly_score=0.95,
    )

    assert report["status"] == "KILL_SWITCH_ACTIVE"
    assert "SEVERE_ANOMALY" in report["state"]["kill_reason"]


def test_kill_manual_trigger_reliability(kill_switch: GlobalKillSwitch) -> None:
    """Verify immediate shutdown on institutional manual trigger request."""
    # Scenario: Manual trigger. Breach.
    report = kill_switch.evaluate_kill_system(
        current_drawdown=0,
        current_absolute_loss=0,
        current_anomaly_score=0,
        manual_trigger=True,
    )

    assert report["status"] == "KILL_SWITCH_ACTIVE"
    assert "MANUAL_HALT" in report["state"]["kill_reason"]


def test_kill_persistent_state_veracity(kill_switch: GlobalKillSwitch) -> None:
    """Verify that the kill switch is non-overrideable once triggered."""
    # 1. Trigger kill.
    kill_switch.evaluate_kill_system(
        current_drawdown=0.3,
        current_absolute_loss=0,
        current_anomaly_score=0,
    )

    # 2. Attempt to evaluate healthy state.
    report = kill_switch.evaluate_kill_system(
        current_drawdown=0,
        current_absolute_loss=0,
        current_anomaly_score=0,
    )

    # State should remain HALTED.
    assert report["status"] == "ALREADY_HALTED"
    assert report["reason"] != ""


def test_kill_telemetry_tracking(kill_switch: GlobalKillSwitch) -> None:
    """Verify situational awareness and forensic kill telemetry indexing."""
    kill_switch.evaluate_kill_system(
        current_drawdown=0.3,
        current_absolute_loss=0,
        current_anomaly_score=0,
    )

    stats = kill_switch.get_kill_telemetry()
    assert stats["is_system_halted"] is True
    assert stats["kill_reason_captured"] != ""
