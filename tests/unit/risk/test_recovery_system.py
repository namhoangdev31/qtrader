import pytest
from qtrader.risk.recovery_system import FailureEvent, RecoveryAction, RecoverySystem


@pytest.fixture
def recovery() -> RecoverySystem:
    return RecoverySystem(loss_limit=-5000.0)


def test_recovery_system_fault_halt(recovery: RecoverySystem) -> None:
    event = FailureEvent(
        strategy_id=None,
        pnl_drawdown=0.0,
        is_risk_high=False,
        is_system_fault=True,
        description="BROKER_DISCONNECT",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.HALT_TRADING
    assert "BROKER_DISCONNECT" in result["reason"]


def test_recovery_pnl_isolation(recovery: RecoverySystem) -> None:
    event = FailureEvent(
        strategy_id="S1",
        pnl_drawdown=-6000.0,
        is_risk_high=False,
        is_system_fault=False,
        description="MAX_DRAWDOWN_REACHED",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.ISOLATE_STRATEGY
    assert result["strategy_id"] == "S1"


def test_recovery_risk_containment(recovery: RecoverySystem) -> None:
    event = FailureEvent(
        strategy_id="S2",
        pnl_drawdown=-1000.0,
        is_risk_high=True,
        is_system_fault=False,
        description="SKEWNESS_ANOMALY",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.REDUCE_EXPOSURE
    assert "RISK_DEGRADATION" in result["reason"]


def test_recovery_normal_conditions(recovery: RecoverySystem) -> None:
    event = FailureEvent(
        strategy_id="S3",
        pnl_drawdown=-100.0,
        is_risk_high=False,
        is_system_fault=False,
        description="HEALTHY",
    )
    result = recovery.propose_recovery(event)
    assert result["action"] == RecoveryAction.NO_ACTION


def test_recovery_telemetry_report(recovery: RecoverySystem) -> None:
    recovery.propose_recovery(FailureEvent("S", 0, False, True, "FAULT"))
    recovery.propose_recovery(FailureEvent("S", -10000, False, False, "LOST"))
    report = recovery.get_recovery_report()
    assert report["total_recoveries"] == 2
    assert report["last_recovery_latency_ms"] < 1000.0
