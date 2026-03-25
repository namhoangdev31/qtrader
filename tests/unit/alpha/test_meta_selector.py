import polars as pl
import pytest

from qtrader.alpha.meta_selector import AlphaMetaSelector

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────
ALPHA_POOL = ["MA_Cross", "RSI_Mean", "Bollinger", "Vol_Surge", "Trend_Follow"]

METRICS_DATA = pl.DataFrame(
    {
        "name": ["MA_Cross", "RSI_Mean", "Bollinger", "Vol_Surge", "Trend_Follow"],
        "sharpe": [1.5, 0.8, 1.2, 2.0, 1.1],
        "ic": [0.05, 0.04, 0.08, 0.02, 0.09],
    }
)

# 1. MA_Cross Score = 1.5 * 0.05 = 0.075
# 2. RSI_Mean Score = 0.8 * 0.04 = 0.032
# 3. Bollinger Score = 1.2 * 0.08 = 0.096
# 4. Vol_Surge Score = 2.0 * 0.02 = 0.040
# 5. Trend_Follow Score = 1.1 * 0.09 = 0.099
# Expected order: Trend_Follow (0.099), Bollinger (0.096), MA_Cross (0.075), ...


def test_meta_selector_ranking_logic() -> None:
    """Verify that alphas are correctly ranked and Top-K selected."""
    k_limit = 2
    selector = AlphaMetaSelector(top_k=k_limit)
    selected = selector.select_best_alphas(ALPHA_POOL, METRICS_DATA)

    # Should only return 2 best
    assert len(selected) == k_limit
    # Ranked order: Trend_Follow (0.099), Bollinger (0.096)
    expected = ["Trend_Follow", "Bollinger"]
    assert selected == expected


def test_meta_selector_empty_metrics_fallback() -> None:
    """Verify fallback to simple pool slice when no metrics provided."""
    k_limit = 3
    selector = AlphaMetaSelector(top_k=k_limit)
    empty_df = pl.DataFrame(schema={"name": pl.Utf8, "sharpe": pl.Float64, "ic": pl.Float64})

    selected = selector.select_best_alphas(ALPHA_POOL, empty_df)
    assert len(selected) == k_limit
    # Should just take first 3 from pool in order of appearance
    assert selected == ALPHA_POOL[:k_limit]


def test_meta_selector_missing_columns_fallback() -> None:
    """Verify fallback when required columns are missing."""
    k_limit = 2
    selector = AlphaMetaSelector(top_k=k_limit)
    bad_df = pl.DataFrame({"name": ["MA_Cross"], "error_metric": [1.0]})

    selected = selector.select_best_alphas(ALPHA_POOL, bad_df)
    assert len(selected) == k_limit
    assert selected == ALPHA_POOL[:k_limit]


def test_meta_selector_pool_diagnostics() -> None:
    """Verify pool diagnostics computation."""
    expected_avg_sharpe = 1.32
    expected_avg_ic = 0.056
    selector = AlphaMetaSelector(top_k=5)
    stats = selector.get_pool_diagnostics(METRICS_DATA)

    assert "avg_sharpe" in stats
    assert "avg_ic" in stats
    assert stats["avg_sharpe"] == pytest.approx(expected_avg_sharpe)
    assert stats["avg_ic"] == pytest.approx(expected_avg_ic)
