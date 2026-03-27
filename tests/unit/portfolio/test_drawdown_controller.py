import pytest

from qtrader.portfolio.drawdown_controller import LiveDrawdownController


@pytest.fixture
def controller() -> LiveDrawdownController:
    """Initialize a LiveDrawdownController for institutional drawdown certification."""
    return LiveDrawdownController()


def test_controller_pass_through_normal(controller: LiveDrawdownController) -> None:
    """Verify that the risk factor is 1.0 when drawdown is 0%."""
    report = controller.calculate_risk_adjustment(100.0, 100.0)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["action"] == "NORMAL"  # noqa: S101
    assert report["metrics"]["risk_adjustment_factor"] == 1.0  # noqa: S101


def test_controller_tier_1_modulation(controller: LiveDrawdownController) -> None:
    """Verify that risk factor is 0.75 when drawdown is 6% (>5%)."""
    # 0.06 DD = (100 - 94) / 100.
    report = controller.calculate_risk_adjustment(94.0, 100.0)

    assert report["action"] == "REDUCE_25"  # noqa: S101
    assert report["metrics"]["risk_adjustment_factor"] == 0.75  # noqa: S101, PLR2004


def test_controller_tier_2_modulation(controller: LiveDrawdownController) -> None:
    """Verify that risk factor is 0.50 when drawdown is 11% (>10%)."""
    # 0.11 DD = (100 - 89) / 100.
    report = controller.calculate_risk_adjustment(89.0, 100.0)

    assert report["action"] == "REDUCE_50"  # noqa: S101
    assert report["metrics"]["risk_adjustment_factor"] == 0.5  # noqa: S101, PLR2004


def test_controller_tier_3_operational_stop(controller: LiveDrawdownController) -> None:
    """Verify that the platform HALTS when drawdown is 16% (>15%)."""
    # 0.16 DD = (100 - 84) / 100.
    report = controller.calculate_risk_adjustment(84.0, 100.0)

    assert report["result"] == "HALTED"  # noqa: S101
    assert report["action"] == "STOP"  # noqa: S101
    assert report["metrics"]["risk_adjustment_factor"] == 0.0  # noqa: S101


def test_controller_mathematical_veracity(controller: LiveDrawdownController) -> None:
    """Verify drawdown calculation and peak equity error handling."""
    # Peak 0 Error.
    report_error = controller.calculate_risk_adjustment(100.0, 0.0)
    assert report_error["result"] == "FAIL"  # noqa: S101

    # Negative DD (Current > Peak).
    report_neg = controller.calculate_risk_adjustment(120.0, 100.0)
    assert report_neg["metrics"]["current_drawdown_percent"] == 0.0  # noqa: S101


def test_controller_telemetry_tracking(controller: LiveDrawdownController) -> None:
    """Verify situational awareness and peak drawdown telemetry indexing."""
    # Normal (at threshold 0.05, 0.05 is REDUCE_25)
    controller.calculate_risk_adjustment(95.0, 100.0)
    controller.calculate_risk_adjustment(80.0, 100.0)  # STOP

    stats = controller.get_drawdown_telemetry()
    assert stats["maxly_historical_drawdown"] == 0.2  # noqa: S101, PLR2004
    assert stats["lockout_active"] is True  # noqa: S101
    assert stats["governance_event_count"] == 2  # noqa: S101, PLR2004
