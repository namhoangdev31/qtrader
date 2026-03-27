import pytest

from qtrader.execution.degradation_handler import ExecutionDegradationHandler


@pytest.fixture
def handler() -> ExecutionDegradationHandler:
    """Initialize an ExecutionDegradationHandler for institutional execution certification."""
    return ExecutionDegradationHandler()


def test_handler_nominal_operation(handler: ExecutionDegradationHandler) -> None:
    """Verify that ideal execution conditions result in NORMAL_OPERATIONS."""
    # S=0, F=1.0, L=0 -> D=0. (0 < 0.2)
    metrics = {"slippage_bps": 0.0, "cumulative_fill_rate": 1.0, "recorded_latency_ms": 0.0}
    report = handler.evaluate_execution_health(metrics)

    assert report["triggered_action"] == "NORMAL_OPERATIONS"  # noqa: S101
    assert report["metrics"]["composite_degradation_score"] == 0.0  # noqa: S101


def test_handler_size_reduction_trigger(handler: ExecutionDegradationHandler) -> None:
    """Verify that moderate slippage triggers a REDUCE_SIZE action."""
    # S = -20bps (S_norm = 1.0). F=1.0. L=0.
    # D = 0.5 * 1.0 + 0.3 * 0 + 0.2 * 0 = 0.5. (0.5 >= 0.5)
    metrics = {"slippage_bps": -20.0, "cumulative_fill_rate": 1.0, "recorded_latency_ms": 0.0}
    report = handler.evaluate_execution_health(metrics)

    assert report["triggered_action"] == "REDUCE_SIZE"  # noqa: S101
    assert report["metrics"]["composite_degradation_score"] == 0.5  # noqa: S101, PLR2004


def test_handler_terminal_strategy_pause(handler: ExecutionDegradationHandler) -> None:
    """Verify that binary failure (e.g. 0% fill rate) triggers a PAUSE_STRATEGY."""
    # Adverse Slippage -40bps (S_norm = 2.0). F=0.0 (F_norm = 1.0). L=1000ms (L_norm = 1.0).
    # D = 0.5*2.0 + 0.3*1.0 + 0.2*1.0 = 1.5. (1.5 >= 1.0)
    metrics = {"slippage_bps": -40.0, "cumulative_fill_rate": 0.0, "recorded_latency_ms": 1000.0}
    report = handler.evaluate_execution_health(metrics)

    assert report["triggered_action"] == "PAUSE_STRATEGY"  # noqa: S101
    assert report["metrics"]["composite_degradation_score"] >= 1.0  # noqa: S101


def test_handler_latency_dominant_degradation(handler: ExecutionDegradationHandler) -> None:
    """Verify that a significant latency spike alone can trigger a delay action."""
    # S=0. F=1.0. L=400ms (L_norm = 1.0 clamped).
    # D = 0.5*0 + 0.3*0 + 0.2*1.0 = 0.2. (0.2 >= 0.2)
    metrics = {"slippage_bps": 0.0, "cumulative_fill_rate": 1.0, "recorded_latency_ms": 400.0}
    report = handler.evaluate_execution_health(metrics)

    assert report["triggered_action"] == "DELAY_EXECUTION"  # noqa: S101


def test_handler_telemetry_tracking(handler: ExecutionDegradationHandler) -> None:
    """Verify situational awareness and health recovery telemetry indexing."""
    m_low = {"slippage_bps": -10.0, "cumulative_fill_rate": 1.0, "recorded_latency_ms": 0.0}
    m_high = {"slippage_bps": -20.0, "cumulative_fill_rate": 1.0, "recorded_latency_ms": 0.0}

    handler.evaluate_execution_health(m_low)  # D=0.25
    handler.evaluate_execution_health(m_high)  # D=0.5

    stats = handler.get_degradation_telemetry()
    assert stats["peak_degradation_captured"] == 0.5  # noqa: S101, PLR2004
    assert stats["triggered_actions_summary"]["REDUCE_SIZE"] == 1  # noqa: S101
    assert stats["governance_regime"] == "REBUILDING_LIQUIDITY"  # noqa: S101
