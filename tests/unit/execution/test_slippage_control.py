import pytest

from qtrader.execution.slippage_control import SlippageControlEngine


@pytest.fixture
def engine() -> SlippageControlEngine:
    """Initialize a SlippageControlEngine for institutional execution certification."""
    return SlippageControlEngine()


def test_engine_direct_market_pass(engine: SlippageControlEngine) -> None:
    """Verify that a small footprint (R <= 0.2) results in DIRECT_MARKET strategy."""
    # Size 10. Liquidity 100. R = 0.1. (0.1 <= 0.2)
    order = {"quantity": 10.0}
    report = engine.generate_execution_plan(order, 100.0)

    assert report["plan"]["selected_strategy"] == "DIRECT_MARKET"
    assert report["plan"]["is_segmenting_active"] is False
    assert report["metrics"]["estimated_impact_ratio"] == 0.1


def test_engine_vwap_routing(engine: SlippageControlEngine) -> None:
    """Verify that a significant footprint results in VWAP strategy."""
    # Size 50. Liquidity 100. R = 0.5. (0.2 < 0.5 <= 1.0)
    order = {"quantity": 50.0}
    report = engine.generate_execution_plan(order, 100.0)

    assert report["plan"]["selected_strategy"] == "VWAP"
    assert report["metrics"]["estimated_impact_ratio"] == 0.5


def test_engine_iceberg_segmenting(engine: SlippageControlEngine) -> None:
    """Verify that an oversized footprint results in ICEBERG_SPLIT strategy."""
    # Size 150. Liquidity 100. R = 1.5. (1.5 > 1.0)
    order = {"quantity": 150.0}
    report = engine.generate_execution_plan(order, 100.0)

    assert report["plan"]["selected_strategy"] == "ICEBERG_SPLIT"
    assert report["plan"]["is_segmenting_active"] is True
    assert report["metrics"]["estimated_impact_ratio"] == 1.5


def test_engine_low_liquidity_safety(engine: SlippageControlEngine) -> None:
    """Verify handling of extremely thin or zero liquidity regimes."""
    # Order 10. Liquidity 0.00000001 (Epsilon handled). R >> 1.0.
    order = {"quantity": 10.0}
    report = engine.generate_execution_plan(order, 0.0)

    assert report["plan"]["selected_strategy"] == "ICEBERG_SPLIT"
    assert report["plan"]["operational_caution"] == "CAUTION_SIGNIFICANT_IMPACT"


def test_engine_telemetry_tracking(engine: SlippageControlEngine) -> None:
    """Verify situational awareness and execution forensics telemetry indexing."""
    engine.generate_execution_plan({"quantity": 10.0}, 100.0)  # R=0.1
    engine.generate_execution_plan({"quantity": 50.0}, 100.0)  # R=0.5

    stats = engine.get_slippage_telemetry()
    assert stats["total_plans_generated"] == 2
    assert stats["avg_impact_ratio_observed"] == 0.3
    assert stats["regime"] == "LIQUIDITY_ADAPTIVE"
