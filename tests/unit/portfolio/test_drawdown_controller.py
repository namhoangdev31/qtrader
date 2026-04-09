import pytest
from qtrader.portfolio.drawdown_controller import LiveDrawdownController


@pytest.fixture
def controller() -> LiveDrawdownController:
    return LiveDrawdownController()


def test_controller_pass_through_normal(controller: LiveDrawdownController) -> None:
    report = controller.calculate_risk_adjustment(100.0, 100.0)
    assert report["result"] == "PASS"
    assert report["action"] == "NORMAL"
    assert report["metrics"]["risk_adjustment_factor"] == 1.0


def test_controller_tier_1_modulation(controller: LiveDrawdownController) -> None:
    report = controller.calculate_risk_adjustment(94.0, 100.0)
    assert report["action"] == "REDUCE_25"
    assert report["metrics"]["risk_adjustment_factor"] == 0.75


def test_controller_tier_2_modulation(controller: LiveDrawdownController) -> None:
    report = controller.calculate_risk_adjustment(89.0, 100.0)
    assert report["action"] == "REDUCE_50"
    assert report["metrics"]["risk_adjustment_factor"] == 0.5


def test_controller_tier_3_operational_stop(controller: LiveDrawdownController) -> None:
    report = controller.calculate_risk_adjustment(84.0, 100.0)
    assert report["result"] == "HALTED"
    assert report["action"] == "STOP"
    assert report["metrics"]["risk_adjustment_factor"] == 0.0


def test_controller_mathematical_veracity(controller: LiveDrawdownController) -> None:
    report_error = controller.calculate_risk_adjustment(100.0, 0.0)
    assert report_error["result"] == "FAIL"
    report_neg = controller.calculate_risk_adjustment(120.0, 100.0)
    assert report_neg["metrics"]["current_drawdown_percent"] == 0.0


def test_controller_telemetry_tracking(controller: LiveDrawdownController) -> None:
    controller.calculate_risk_adjustment(95.0, 100.0)
    controller.calculate_risk_adjustment(80.0, 100.0)
    stats = controller.get_drawdown_telemetry()
    assert stats["maxly_historical_drawdown"] == 0.2
    assert stats["lockout_active"] is True
    assert stats["governance_event_count"] == 2
