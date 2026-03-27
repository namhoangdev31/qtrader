import pytest

from qtrader.portfolio.capital_guard import CapitalPreservationGuard


@pytest.fixture
def guard() -> CapitalPreservationGuard:
    """Initialize a CapitalPreservationGuard for institutional hard-stop certification."""
    return CapitalPreservationGuard()


def test_guard_integrity_pass_safe(guard: CapitalPreservationGuard) -> None:
    """Verify that the status is SAFE when loss is below the institutional limit."""
    # Loss = 100 - 95 = 5. Limit 10. (5 < 10)
    report = guard.check_integrity(100.0, 95.0, 10.0)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["guard_state"] == "SAFE"  # noqa: S101
    assert report["metrics"]["absolute_capital_loss"] == 5.0  # noqa: S101, PLR2004


def test_guard_integrity_fail_halt(guard: CapitalPreservationGuard) -> None:
    """Verify that the status is HALT when loss exceeds the institutional limit."""
    # Loss = 100 - 85 = 15. Limit 10. (15 > 10)
    report = guard.check_integrity(100.0, 85.0, 10.0)

    assert report["result"] == "BREACHED"  # noqa: S101
    assert report["guard_state"] == "HALT"  # noqa: S101
    assert report["metrics"]["absolute_capital_loss"] == 15.0  # noqa: S101, PLR2004


def test_guard_zero_capital_handling(guard: CapitalPreservationGuard) -> None:
    """Verify that the platform HALTs when current capital reaches zero."""
    # Loss = 100 - 0 = 100. Limit 10.
    report = guard.check_integrity(100.0, 0.0, 10.0)

    assert report["guard_state"] == "HALT"  # noqa: S101


def test_guard_fractional_precision_breach(guard: CapitalPreservationGuard) -> None:
    """Verify that epsilon breaches are correctly caught."""
    # Loss = 100.0 - 89.99 = 10.01. Limit 10.0
    report = guard.check_integrity(100.0, 89.99, 10.0)

    assert report["result"] == "BREACHED"  # noqa: S101
    assert report["metrics"]["absolute_capital_loss"] == pytest.approx(10.01)  # noqa: S101


def test_guard_telemetry_tracking(guard: CapitalPreservationGuard) -> None:
    """Verify situational awareness and peak loss telemetry indexing."""
    guard.check_integrity(100.0, 95.0, 10.0)  # PASS
    guard.check_integrity(100.0, 80.0, 10.0)  # HALT

    stats = guard.get_guard_telemetry()
    assert stats["total_halt_events"] == 1  # noqa: S101
    assert stats["historical_peak_loss"] == 20.0  # noqa: S101, PLR2004
    assert stats["protection_active"] is True  # noqa: S101
    assert stats["status"] == "CAPITAL_GOVERNANCE"  # noqa: S101
