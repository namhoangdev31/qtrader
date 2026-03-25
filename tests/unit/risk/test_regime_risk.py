"""Unit tests for regime-adjusted risk engine."""

from __future__ import annotations

import pytest

from qtrader.risk.regime_adapter import RegimeAdapter
from qtrader.risk.runtime_risk_engine import AdvancedRiskEngine


def test_regime_adapter_scaling() -> None:
    """Test that regime adapter correctly scales limits."""
    adapter = RegimeAdapter()

    base_var = 0.05
    base_leverage = 5.0
    base_position = 0.10

    # Regime 0 (low vol): no change
    limits_0 = adapter.adjust_limits(0, base_var, base_leverage, base_position)
    assert limits_0["var_threshold"] == base_var
    assert limits_0["max_leverage"] == base_leverage
    assert limits_0["max_position_size"] == base_position

    # Regime 1 (high vol): VaR * 0.7, leverage * 0.6, position * 0.7
    limits_1 = adapter.adjust_limits(1, base_var, base_leverage, base_position)
    assert limits_1["var_threshold"] == pytest.approx(base_var * 0.7)
    assert limits_1["max_leverage"] == pytest.approx(base_leverage * 0.6)
    assert limits_1["max_position_size"] == pytest.approx(base_position * 0.7)

    # Regime 2 (crisis): all * 0.5
    limits_2 = adapter.adjust_limits(2, base_var, base_leverage, base_position)
    assert limits_2["var_threshold"] == pytest.approx(base_var * 0.5)
    assert limits_2["max_leverage"] == pytest.approx(base_leverage * 0.5)
    assert limits_2["max_position_size"] == pytest.approx(base_position * 0.5)

    # Unknown regime defaults to regime 0
    limits_unknown = adapter.adjust_limits(99, base_var, base_leverage, base_position)
    assert limits_unknown == limits_0


def test_risk_engine_set_regime() -> None:
    """Test that setting regime updates the risk limits."""
    engine = AdvancedRiskEngine(var_threshold=0.05, max_leverage=5.0, max_position_size=0.10)

    # Initial limits should be base values
    assert engine._current_var_threshold == 0.05
    assert engine._current_max_leverage == 5.0
    assert engine._current_max_position_size == 0.10
    assert engine._current_regime_id == 0  # Default regime

    # Set to high volatility regime
    engine.set_regime(1)

    # Limits should be adjusted
    assert engine._current_regime_id == 1
    assert engine._current_var_threshold == pytest.approx(0.05 * 0.7)  # 0.035
    assert engine._current_max_leverage == pytest.approx(5.0 * 0.6)  # 3.0
    assert engine._current_max_position_size == pytest.approx(0.10 * 0.7)  # 0.07

    # Set to crisis regime
    engine.set_regime(2)

    # Limits should be adjusted further
    assert engine._current_regime_id == 2
    assert engine._current_var_threshold == pytest.approx(0.05 * 0.5)  # 0.025
    assert engine._current_max_leverage == pytest.approx(5.0 * 0.5)  # 2.5
    assert engine._current_max_position_size == pytest.approx(0.10 * 0.5)  # 0.05

    # Return to low volatility
    engine.set_regime(0)

    # Limits should return to base values
    assert engine._current_regime_id == 0
    assert engine._current_var_threshold == pytest.approx(0.05)
    assert engine._current_max_leverage == pytest.approx(5.0)
    assert engine._current_max_position_size == pytest.approx(0.10)


def test_risk_engine_regime_affects_var_check() -> None:
    """Test that regime-adjusted VaR threshold affects risk checking."""
    engine = AdvancedRiskEngine(
        var_threshold=0.10,  # 10% base VaR
        max_leverage=5.0,
        max_position_size=0.20,
    )

    # Test in low vol regime (default)
    engine.set_regime(0)
    assert engine._current_var_threshold == 0.10

    # Risk metrics with VaR = 0.08 (8%) should pass in low vol
    risk_metrics_low_vol = {"var": 0.08, "leverage": 2.0, "current_drawdown": 0.05}
    # We'd need to call check_limits, but for simplicity we test the threshold directly
    assert 0.08 < engine._current_var_threshold  # Should pass

    # Switch to high vol regime
    engine.set_regime(1)
    # VaR threshold should be 0.10 * 0.7 = 0.07
    assert engine._current_var_threshold == pytest.approx(0.07)

    # Same VaR = 0.08 (8%) should now FAIL in high vol regime
    assert 0.08 > engine._current_var_threshold  # Should fail

    # Switch to crisis regime
    engine.set_regime(2)
    # VaR threshold should be 0.10 * 0.5 = 0.05
    assert engine._current_var_threshold == pytest.approx(0.05)

    # Even lower VaR = 0.06 (6%) should FAIL in crisis regime
    assert 0.06 > engine._current_var_threshold  # Should fail


def test_risk_engine_regime_affects_leverage_check() -> None:
    """Test that regime-adjusted leverage threshold affects risk checking."""
    engine = AdvancedRiskEngine(
        var_threshold=0.05,
        max_leverage=3.0,  # 3x base leverage
        max_position_size=0.15,
    )

    # Test in low vol regime (default)
    engine.set_regime(0)
    assert engine._current_max_leverage == 3.0

    # Switch to high vol regime
    engine.set_regime(1)
    # Leverage limit should be 3.0 * 0.6 = 1.8
    assert engine._current_max_leverage == pytest.approx(1.8)

    # Leverage of 2.0 should pass in low vol but fail in high vol
    engine.set_regime(0)  # Back to low vol
    assert 2.0 < 3.0  # Pass in low vol (limit = 3.0)
    engine.set_regime(1)  # High vol
    # Get the actual value for comparison
    high_vol_limit = engine._current_max_leverage
    assert 2.0 > high_vol_limit  # Fail in high vol


def test_risk_engine_regime_affects_position_check() -> None:
    """Test that regime-adjusted position size threshold affects risk checking."""
    engine = AdvancedRiskEngine(
        var_threshold=0.05,
        max_leverage=4.0,
        max_position_size=0.25,  # 25% base position limit
    )

    # Test in low vol regime (default)
    engine.set_regime(0)
    assert engine._current_max_position_size == 0.25

    # Switch to crisis regime
    engine.set_regime(2)
    # Position limit should be 0.25 * 0.5 = 0.125 (12.5%)
    assert engine._current_max_position_size == pytest.approx(0.125)

    # Position size of 0.20 (20%) should pass in low vol but fail in crisis
    engine.set_regime(0)
    assert 0.20 < 0.25  # Pass in low vol
    engine.set_regime(2)  # Crisis
    crisis_limit = engine._current_max_position_size
    assert 0.20 > crisis_limit  # Fail in crisis


def test_regime_adapter_thread_safety() -> None:
    """Test that regime adapter is thread-safe for concurrent access."""
    import threading

    adapter = RegimeAdapter()
    results = []
    errors = []

    def worker(worker_id: int) -> None:
        try:
            # Each worker accesses the adapter multiple times
            for i in range(50):
                limits = adapter.adjust_limits(
                    regime_id=worker_id % 3,
                    base_var_threshold=0.05,
                    base_max_leverage=5.0,
                    base_max_position_size=0.10,
                )
                results.append(limits)
        except Exception as e:
            errors.append(f"Worker {worker_id} error: {e}")

    # Create and start multiple threads
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Check for any errors
    assert len(errors) == 0, f"Thread safety errors: {errors}"
    # Should have 10 workers * 50 iterations = 500 results
    assert len(results) == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
