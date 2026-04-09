import pytest
from qtrader.portfolio.position_sizing import RiskAdaptivePositionSizer


@pytest.fixture
def sizer() -> RiskAdaptivePositionSizer:
    return RiskAdaptivePositionSizer(size_max=1.0)


def test_sizer_high_vol_throttling(sizer: RiskAdaptivePositionSizer) -> None:
    report = sizer.calculate_adaptive_size(0.1, 0.1, {"target_vol": 0.01})
    assert report["result"] == "PASS"
    assert report["metrics"]["calculated_position_size"] == 0.01
    assert report["metrics"]["volatility_modulation_factor"] == 0.1


def test_sizer_low_vol_expansion(sizer: RiskAdaptivePositionSizer) -> None:
    report = sizer.calculate_adaptive_size(0.1, 0.005, {"target_vol": 0.01})
    assert report["metrics"]["calculated_position_size"] == 0.2
    assert report["metrics"]["volatility_modulation_factor"] == 2.0


def test_sizer_max_exposure_cap(sizer: RiskAdaptivePositionSizer) -> None:
    report = sizer.calculate_adaptive_size(0.1, 0.0001, {"target_vol": 0.01})
    assert report["metrics"]["calculated_position_size"] == 1.0
    assert report["governance"]["size_max_applied"] == 1.0


def test_sizer_zero_vol_safety(sizer: RiskAdaptivePositionSizer) -> None:
    report = sizer.calculate_adaptive_size(0.1, 0.0)
    assert report["governance"]["volatility_floor_active"] is True
    assert report["metrics"]["calculated_position_size"] > 0


def test_sizer_telemetry_tracking(sizer: RiskAdaptivePositionSizer) -> None:
    sizer.calculate_adaptive_size(0.1, 0.01)
    sizer.calculate_adaptive_size(0.1, 0.1)
    stats = sizer.get_sizing_telemetry()
    assert stats["lifecycle_decision_count"] == 2
    assert stats["avg_position_size_observed"] == 0.055
    assert stats["avg_volatility_observed"] == 0.055
