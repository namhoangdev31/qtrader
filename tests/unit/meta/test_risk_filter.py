import polars as pl
import pytest

from qtrader.meta.risk_filter import RiskFilter

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

STRATEGY_METRICS = pl.DataFrame(
    {
        "config_id": [1, 2, 3, 4],
        "max_drawdown": [0.05, 0.12, 0.25, 0.10],  # 3 is too risky (25% > 15%)
        "var": [0.01, 0.02, 0.02, 0.08],  # 4 is too volatile (8% > 3%)
    }
)

# Threshold Configuration
MAX_DD = 0.15
MAX_VAR = 0.03


def test_risk_filter_filtering_logic() -> None:
    """Verify that strategies exceeding risk thresholds are correctly removed."""
    filter_eng = RiskFilter()
    safe_ones = filter_eng.filter_risky_candidates(
        STRATEGY_METRICS,
        max_drawdown_threshold=MAX_DD,
        var_threshold=MAX_VAR,
    )

    # Strategies 1 and 2 should pass
    # Strategy 3 fails on MDD (0.25 > 0.15)
    # Strategy 4 fails on VaR (0.08 > 0.03)
    expected_ids = [1, 2]
    assert len(safe_ones) == len(expected_ids)
    assert set(safe_ones["config_id"]) == set(expected_ids)


def test_risk_filter_capital_haircut() -> None:
    """Verify that capital haircut correctly scales down exposure for higher risk."""
    filter_eng = RiskFilter()
    base = 0.1
    enriched = filter_eng.calculate_capital_haircut(STRATEGY_METRICS, base_haircut=base)

    # Strategy 1 (MDD 0.05), Base 0.1 -> Haircut 0.15 -> Multiplier 0.85
    val_0 = 0.85
    assert enriched["capital_multiplier"][0] == pytest.approx(val_0)

    # Strategy 3 (MDD 0.25), Base 0.1 -> Haircut 0.35 -> Multiplier 0.65
    val_2 = 0.65
    assert enriched["capital_multiplier"][2] == pytest.approx(val_2)


def test_risk_filter_empty_robustness() -> None:
    """Ensure robustness to empty metrics input."""
    filter_eng = RiskFilter()
    empty = pl.DataFrame()

    res = filter_eng.filter_risky_candidates(empty)
    assert res.is_empty()

    res_h = filter_eng.calculate_capital_haircut(empty)
    assert res_h.is_empty()
