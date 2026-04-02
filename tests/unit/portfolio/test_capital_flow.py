import pytest

from qtrader.portfolio.capital_flow import CapitalFlowManager


@pytest.fixture
def manager() -> CapitalFlowManager:
    """Initialize a CapitalFlowManager for institutional treasury certification."""
    return CapitalFlowManager()


def test_flow_standard_calculation(manager: CapitalFlowManager) -> None:
    """Verify that capital accurately reflects the flow summation."""
    # Start 1000. Deposit 500. Withdraw 200. Total 1300.
    current = 1000.0
    report = manager.process_flow_requests(current, deposit_amount=500.0, withdrawal_amount=200.0)

    assert report["treasury"]["updated_net_capital"] == 1300.0
    assert report["treasury"]["net_flow_basis"] == 300.0


def test_flow_exposure_gating(manager: CapitalFlowManager) -> None:
    """Verify that withdrawals are blocked when has_open_exposure is True."""
    # Current 1000. Withdrawal 100. Exposure TRUE. Result: Denied.
    report = manager.process_flow_requests(1000.0, withdrawal_amount=100.0, has_open_exposure=True)

    assert report["treasury"]["updated_net_capital"] == 1000.0
    assert report["forensics"]["rejection_reason"] == "DENIED_OPEN_EXPOSURE"
    assert report["forensics"]["withdrawals_approved"] == 0.0


def test_flow_insufficient_liquidity_gating(manager: CapitalFlowManager) -> None:
    """Verify rejection of withdrawals exceeding available capital."""
    # Current 100. Withdrawal 200. Result: Denied (Insolvent).
    report = manager.process_flow_requests(100.0, withdrawal_amount=200.0)

    assert report["treasury"]["updated_net_capital"] == 100.0
    assert report["forensics"]["rejection_reason"] == "DENIED_INSUFFICIENT_LIQUIDITY"


def test_flow_net_telemetry(manager: CapitalFlowManager) -> None:
    """Verify situational awareness and treasury forensics telemetry indexing."""
    manager.process_flow_requests(1000.0, deposit_amount=500.0)  # V1: +500
    manager.process_flow_requests(1500.0, withdrawal_amount=200.0)  # V2: -200

    stats = manager.get_flow_telemetry()
    assert stats["cumulative_funding_shift"] == 300.0
    assert stats["liquidity_regime"] == "STABLE"


def test_flow_rejection_telemetry(manager: CapitalFlowManager) -> None:
    """Verify accumulation of governance denial artifacts."""
    for _ in range(6):
        manager.process_flow_requests(1000.0, withdrawal_amount=10000.0)  # Insolvent

    stats = manager.get_flow_telemetry()
    assert stats["denied_withdrawal_events"] == 6
    assert stats["liquidity_regime"] == "CONSTRAINED_SOLVENCY"
