import polars as pl
import pytest

from qtrader.meta.orchestrator import SystemOrchestrator

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

SIGNALS_DF = pl.DataFrame(
    {
        "m_gbdt": [0.5, 0.2, 0.8],
        "m_rl": [-0.1, 0.4, 0.6],
        "m_linear": [0.0, 0.0, 0.0],
    }
)

# Relative performance weights (Sharpe, etc.)
WEIGHTS = {"m_gbdt": 0.8, "m_rl": 0.2, "m_linear": 0.0}


def test_orchestrator_ensemble_aggregation() -> None:
    """Verify that multiple signals are correctly weighted and combined."""
    orchestrator = SystemOrchestrator()
    ensemble = orchestrator.compute_ensemble_signal(SIGNALS_DF, WEIGHTS)

    expected_len = 3
    assert len(ensemble) == expected_len

    # Row 0: (0.5 * 0.8) + (-0.1 * 0.2) + (0 * 0) = 0.4 - 0.02 = 0.38
    # Divided by total weight (0.8 + 0.2 + 0.0) = 1.0
    val_0 = 0.38
    assert ensemble[0] == pytest.approx(val_0)

    # Row 2: (0.8 * 0.8) + (0.6 * 0.2) = 0.64 + 0.12 = 0.76
    val_2 = 0.76
    assert ensemble[2] == pytest.approx(val_2)


def test_orchestrator_weight_adaptation() -> None:
    """Verify that performance metrics correctly derive new weights."""
    metrics = pl.DataFrame(
        {
            "model_id": ["m_gbdt", "m_rl"],
            "sharpe": [2.0, 1.0],  # 2:1 Ratio
        }
    )

    orchestrator = SystemOrchestrator()
    new_weights = orchestrator.adapt_weights(metrics, target_metric="sharpe")

    # Total performance = 3.0
    expected_gbdt = 2.0 / 3.0
    expected_rl = 1.0 / 3.0
    assert new_weights["m_gbdt"] == pytest.approx(expected_gbdt)
    assert new_weights["m_rl"] == pytest.approx(expected_rl)


def test_orchestrator_empty_metrics_fallback() -> None:
    """Ensure equal weights are returned if metrics are zero or negative."""
    metrics = pl.DataFrame(
        {
            "model_id": ["m1", "m2"],
            "sharpe": [-1.5, -0.5],  # All negative
        }
    )

    orchestrator = SystemOrchestrator()
    # Should fallback to equal weight
    new_weights = orchestrator.adapt_weights(metrics, target_metric="sharpe")

    expected_w = 0.5
    assert new_weights["m1"] == expected_w
    assert new_weights["m2"] == expected_w


def test_orchestrator_empty_dataframe_protection() -> None:
    """Verify robustness to empty data input."""
    orchestrator = SystemOrchestrator()
    empty = pl.DataFrame()

    res_signal = orchestrator.compute_ensemble_signal(empty, {})
    assert len(res_signal) == 0

    res_weights = orchestrator.adapt_weights(empty)
    assert res_weights == {}
