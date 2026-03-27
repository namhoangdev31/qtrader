import pytest

from qtrader.certification.shadow_validation import MarketRegime, ShadowValidationEngine


@pytest.fixture
def engine() -> ShadowValidationEngine:
    """Initialize a ShadowValidationEngine for institutional strategy certification."""
    return ShadowValidationEngine(sigma_max_bound=0.05)


def test_shadow_engine_multi_regime_pass(engine: ShadowValidationEngine) -> None:
    """Verify that outperforming baseline across all 4 regimes results in a PASS status."""
    regime_results = {
        MarketRegime.TRENDING: {"strategy_pnl": 0.05, "baseline_pnl": 0.03},
        MarketRegime.MEAN_REVERTING: {"strategy_pnl": 0.02, "baseline_pnl": 0.01},
        MarketRegime.HIGH_VOLATILITY: {"strategy_pnl": 0.08, "baseline_pnl": 0.06},
        MarketRegime.LOW_LIQUIDITY: {"strategy_pnl": 0.01, "baseline_pnl": 0.005},
    }

    report = engine.evaluate_shadow_performance(regime_results)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["metrics"]["regime_diversity_met"] is True  # noqa: S101
    assert report["metrics"]["average_performance_delta"] > 0  # noqa: S101


def test_shadow_engine_regime_failure_block(engine: ShadowValidationEngine) -> None:
    """Verify that underperforming in a single regime results in a FAIL status."""
    regime_results = {
        MarketRegime.TRENDING: {"strategy_pnl": 0.05, "baseline_pnl": 0.03},
        MarketRegime.MEAN_REVERTING: {"strategy_pnl": 0.00, "baseline_pnl": 0.01},  # FAILURE
        MarketRegime.HIGH_VOLATILITY: {"strategy_pnl": 0.08, "baseline_pnl": 0.06},
        MarketRegime.LOW_LIQUIDITY: {"strategy_pnl": 0.01, "baseline_pnl": 0.005},
    }

    report = engine.evaluate_shadow_performance(regime_results)

    assert report["result"] == "FAIL"  # noqa: S101


def test_shadow_engine_variance_breach_detection(engine: ShadowValidationEngine) -> None:
    """Verify that performance variance exceeding sigma_max results in a FAIL status."""
    # High variance in deltas: 0.1, -0.05, 0.4, -0.2
    regime_results = {
        MarketRegime.TRENDING: {"strategy_pnl": 0.1, "baseline_pnl": 0.0},
        MarketRegime.MEAN_REVERTING: {"strategy_pnl": -0.05, "baseline_pnl": 0.0},
        MarketRegime.HIGH_VOLATILITY: {"strategy_pnl": 0.4, "baseline_pnl": 0.0},
        MarketRegime.LOW_LIQUIDITY: {"strategy_pnl": -0.2, "baseline_pnl": 0.0},
    }

    report = engine.evaluate_shadow_performance(regime_results)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["metrics"]["variance_consistency_met"] is False  # noqa: S101


def test_shadow_engine_diversity_compliance(engine: ShadowValidationEngine) -> None:
    """Verify that missing regimes result in failed certification (Diversity Breach)."""
    # Only 2 regimes provided
    regime_results = {
        MarketRegime.TRENDING: {"strategy_pnl": 0.05, "baseline_pnl": 0.03},
        MarketRegime.MEAN_REVERTING: {"strategy_pnl": 0.02, "baseline_pnl": 0.01},
    }

    report = engine.evaluate_shadow_performance(regime_results)

    assert report["metrics"]["regime_diversity_met"] is False  # noqa: S101
    assert report["result"] == "FAIL"  # noqa: S101


def test_shadow_engine_telemetry_tracking(engine: ShadowValidationEngine) -> None:
    """Verify situational awareness and cumulative delta tracking."""
    # Run 1: 4 regimes
    regime_results = {r: {"strategy_pnl": 0.02, "baseline_pnl": 0.01} for r in MarketRegime}
    engine.evaluate_shadow_performance(regime_results)

    stats = engine.get_shadow_telemetry()
    assert stats["total_regime_observations"] == 4  # noqa: S101, PLR2004
    assert stats["weighted_cumulative_delta"] == 0.01  # noqa: S101, PLR2004
    assert stats["status"] == "SHADOW_CERTIFICATION"  # noqa: S101
