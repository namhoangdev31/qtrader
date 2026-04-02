import pytest

from qtrader.portfolio.position_sizing import RiskAdaptivePositionSizer


@pytest.fixture
def sizer() -> RiskAdaptivePositionSizer:
    """Initialize a RiskAdaptivePositionSizer for institutional sizing certification."""
    return RiskAdaptivePositionSizer(size_max=1.0)


def test_sizer_high_vol_throttling(sizer: RiskAdaptivePositionSizer) -> None:
    """Verify that increasing volatility leads to correctly scaled smaller sizes."""
    # Base 0.1. Target 0.01. Vol 0.1. Factor = 0.01 / 0.1 = 0.1.
    # Adjusted Size = 0.1 * 0.1 = 0.01.
    report = sizer.calculate_adaptive_size(0.1, 0.1, {"target_vol": 0.01})

    assert report["result"] == "PASS"
    assert report["metrics"]["calculated_position_size"] == 0.01
    assert report["metrics"]["volatility_modulation_factor"] == 0.1


def test_sizer_low_vol_expansion(sizer: RiskAdaptivePositionSizer) -> None:
    """Verify larger sizing when volatility is low."""
    # Base 0.1. Target 0.01. Vol 0.005. Factor = 0.01 / 0.005 = 2.0.
    # Adjusted Size = 0.1 * 2.0 = 0.2.
    report = sizer.calculate_adaptive_size(0.1, 0.005, {"target_vol": 0.01})

    assert report["metrics"]["calculated_position_size"] == 0.2
    assert report["metrics"]["volatility_modulation_factor"] == 2.0


def test_sizer_max_exposure_cap(sizer: RiskAdaptivePositionSizer) -> None:
    """Verify that derived size never exceeds the institutional max_size."""
    # Base 0.1. Target 0.01. Vol 0.0001 (Very low). Factor = 100.
    # Raw Size = 10.0. Clamped to Max 1.0.
    report = sizer.calculate_adaptive_size(0.1, 0.0001, {"target_vol": 0.01})

    assert report["metrics"]["calculated_position_size"] == 1.0
    assert report["governance"]["size_max_applied"] == 1.0


def test_sizer_zero_vol_safety(sizer: RiskAdaptivePositionSizer) -> None:
    """Verify handling of extremely low or zero volatility floors."""
    report = sizer.calculate_adaptive_size(0.1, 0.0)  # Zero Vol

    assert report["governance"]["volatility_floor_active"] is True
    assert report["metrics"]["calculated_position_size"] > 0


def test_sizer_telemetry_tracking(sizer: RiskAdaptivePositionSizer) -> None:
    """Verify situational awareness and peak leverage telemetry indexing."""
    sizer.calculate_adaptive_size(0.1, 0.01)  # Factor 1.0 -> Size 0.1
    sizer.calculate_adaptive_size(0.1, 0.10)  # Factor 0.1 -> Size 0.01

    stats = sizer.get_sizing_telemetry()
    assert stats["lifecycle_decision_count"] == 2
    assert stats["avg_position_size_observed"] == 0.055
    assert stats["avg_volatility_observed"] == 0.055
