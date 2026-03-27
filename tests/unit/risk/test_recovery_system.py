import pytest

from qtrader.risk.recovery_system import FailureEvent, RecoveryAction, RecoverySystem


@pytest.fixture
def recovery() -> RecoverySystem:
    """Initialize RecoverySystem with industrial defaults (5k loss limit)."""
    return RecoverySystem(loss_limit=-5000.0)


def test_recovery_system_fault_halt(recovery: RecoverySystem) -> None:
    """Verify that a critical system fault triggers a global trading halt."""
    event = FailureEvent(
        strategy_id=None,
        pnl_drawdown=0.0,
        is_risk_high=False,
        is_system_fault=True,
        description="BROKER_DISCONNECT",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.HALT_TRADING  # noqa: S101
    assert "BROKER_DISCONNECT" in result["reason"]  # noqa: S101


def test_recovery_pnl_isolation(recovery: RecoverySystem) -> None:
    """Verify that a strategy breaching the loss limit is ISOLATED."""
    event = FailureEvent(
        strategy_id="S1",
        pnl_drawdown=-6000.0,  # < -5000.0
        is_risk_high=False,
        is_system_fault=False,
        description="MAX_DRAWDOWN_REACHED",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.ISOLATE_STRATEGY  # noqa: S101
    assert result["strategy_id"] == "S1"  # noqa: S101


def test_recovery_risk_containment(recovery: RecoverySystem) -> None:
    """Verify that high risk warnings trigger PROACTIVE EXPOSURE REDUCTION."""
    event = FailureEvent(
        strategy_id="S2",
        pnl_drawdown=-1000.0,
        is_risk_high=True,
        is_system_fault=False,
        description="SKEWNESS_ANOMALY",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.REDUCE_EXPOSURE  # noqa: S101
    assert "RISK_DEGRADATION" in result["reason"]  # noqa: S101


def test_recovery_normal_conditions(recovery: RecoverySystem) -> None:
    """Verify no action is proposed during normal operating conditions."""
    event = FailureEvent(
        strategy_id="S3",
        pnl_drawdown=-100.0,
        is_risk_high=False,
        is_system_fault=False,
        description="HEALTHY",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.NO_ACTION  # noqa: S101


def test_recovery_telemetry_report(recovery: RecoverySystem) -> None:
    """Verify situational awareness telemetry tracking of recoveries."""
    # 1. HALT
    recovery.propose_recovery(FailureEvent("S", 0, False, True, "FAULT"))
    # 2. ISOLATE
    recovery.propose_recovery(FailureEvent("S", -10000, False, False, "LOST"))

    report = recovery.get_recovery_report()
    assert report["total_recoveries"] == 2  # noqa: S101, PLR2004
    assert report["last_recovery_latency_ms"] < 1000.0  # noqa: S101, PLR2004
