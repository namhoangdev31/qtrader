import pytest

from qtrader.analytics.fund_fee_engine import FeeCalculationEngine


@pytest.fixture
def engine() -> FeeCalculationEngine:
    """Initialize a FeeCalculationEngine for institutional financial certification."""
    return FeeCalculationEngine()


def test_fee_management_accuracy(engine: FeeCalculationEngine) -> None:
    """Verify that the management fee reflects the NAV scalar."""
    # NAV 1000. Rate 200 bps (2%). Fee = 1000 * 0.02 = 20.
    report = engine.calculate_operational_fees(1000.0, 0.0, 0.0, mgmt_rate_bps=200.0)

    assert report["fees"]["total_management_fee"] == 20.0
    assert report["fees"]["institutional_total"] == 20.0


def test_fee_performance_hwm_gating(engine: FeeCalculationEngine) -> None:
    """Verify that the performance fee accurately triggers above the HWM."""
    # Profit 500. HWM 0. Rate 20%. Fee = 500 * 0.2 = 100.
    report = engine.calculate_operational_fees(
        1000.0, 500.0, 0.0, mgmt_rate_bps=0.0, perf_rate_pct=20.0
    )

    assert report["fees"]["total_performance_fee"] == 100.0
    assert report["hwm_forensics"]["updated_hwm_basis"] == 500.0


def test_fee_performance_no_charge_during_recovery(engine: FeeCalculationEngine) -> None:
    """Verify that no performance fee is charged during capital recovery (PnL < HWM)."""
    # Profit 500. HWM 1000. Result: No perf fee.
    report = engine.calculate_operational_fees(
        10000.0, 500.0, 1000.0, mgmt_rate_bps=0.0, perf_rate_pct=20.0
    )

    assert report["fees"]["total_performance_fee"] == 0.0
    assert report["hwm_forensics"]["updated_hwm_basis"] == 1000.0


def test_fee_hwm_persistence(engine: FeeCalculationEngine) -> None:
    """Verify that the High-Water Mark correctly updates and persists peaks."""
    # Step 1: Reach 500 profit. HWM = 500.
    engine.calculate_operational_fees(1000.0, 500.0, 0.0)

    # Step 2: Drop to 300 profit. HWM remains 500.
    report = engine.calculate_operational_fees(1000.0, 300.0, 500.0)
    assert report["hwm_forensics"]["updated_hwm_basis"] == 500.0

    # Step 3: Rise to 800 profit. HWM = 800.
    report = engine.calculate_operational_fees(1000.0, 800.0, 500.0)
    assert report["hwm_forensics"]["updated_hwm_basis"] == 800.0


def test_fee_telemetry_tracking(engine: FeeCalculationEngine) -> None:
    """Verify situational awareness and forensic fee telemetry indexing."""
    # Fee 110 + Fee 70
    engine.calculate_operational_fees(1000.0, 500.0, 0.0, mgmt_rate_bps=100.0, perf_rate_pct=20.0)
    engine.calculate_operational_fees(1000.0, 800.0, 500.0, mgmt_rate_bps=100.0, perf_rate_pct=20.0)

    stats = engine.get_fee_telemetry()
    assert stats["total_fees_accumulated"] == 180.0
    assert stats["peak_hwm_observed"] == 800.0
