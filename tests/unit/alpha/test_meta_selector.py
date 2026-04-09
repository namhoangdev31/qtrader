import polars as pl
import pytest
from qtrader.alpha.meta_selector import AlphaMetaSelector

ALPHA_POOL = ["MA_Cross", "RSI_Mean", "Bollinger", "Vol_Surge", "Trend_Follow"]
METRICS_DATA = pl.DataFrame(
    {
        "name": ["MA_Cross", "RSI_Mean", "Bollinger", "Vol_Surge", "Trend_Follow"],
        "sharpe": [1.5, 0.8, 1.2, 2.0, 1.1],
        "ic": [0.05, 0.04, 0.08, 0.02, 0.09],
    }
)


def test_meta_selector_ranking_logic() -> None:
    k_limit = 2
    selector = AlphaMetaSelector(top_k=k_limit)
    selected = selector.select_best_alphas(ALPHA_POOL, METRICS_DATA)
    assert len(selected) == k_limit
    expected = ["Trend_Follow", "Bollinger"]
    assert selected == expected


def test_meta_selector_empty_metrics_fallback() -> None:
    k_limit = 3
    selector = AlphaMetaSelector(top_k=k_limit)
    empty_df = pl.DataFrame(schema={"name": pl.Utf8, "sharpe": pl.Float64, "ic": pl.Float64})
    selected = selector.select_best_alphas(ALPHA_POOL, empty_df)
    assert len(selected) == k_limit
    assert selected == ALPHA_POOL[:k_limit]


def test_meta_selector_missing_columns_fallback() -> None:
    k_limit = 2
    selector = AlphaMetaSelector(top_k=k_limit)
    bad_df = pl.DataFrame({"name": ["MA_Cross"], "error_metric": [1.0]})
    selected = selector.select_best_alphas(ALPHA_POOL, bad_df)
    assert len(selected) == k_limit
    assert selected == ALPHA_POOL[:k_limit]


def test_meta_selector_pool_diagnostics() -> None:
    expected_avg_sharpe = 1.32
    expected_avg_ic = 0.056
    selector = AlphaMetaSelector(top_k=5)
    stats = selector.get_pool_diagnostics(METRICS_DATA)
    assert "avg_sharpe" in stats
    assert "avg_ic" in stats
    assert stats["avg_sharpe"] == pytest.approx(expected_avg_sharpe)
    assert stats["avg_ic"] == pytest.approx(expected_avg_ic)
