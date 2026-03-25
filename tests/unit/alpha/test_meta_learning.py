import polars as pl
import pytest

from qtrader.alpha.meta_learning import MetaAlphaSelector


@pytest.fixture
def wide_performance_data() -> pl.DataFrame:
    """Mock performance data in wide format."""
    # Regime 0 (Bull): Alpha A > Alpha B
    # Regime 1 (Bear): Alpha B > Alpha A
    return pl.DataFrame(
        {
            "regime": [0, 0, 0, 1, 1, 1],
            "alpha_a": [0.05, 0.06, 0.04, -0.01, -0.02, 0.0],
            "alpha_b": [0.01, 0.02, 0.03, 0.04, 0.05, 0.03],
        }
    )


def test_meta_selector_wide_fit(wide_performance_data: pl.DataFrame) -> None:
    """Verify fit and recommendation with wide format data."""
    selector = MetaAlphaSelector()
    selector.fit(
        wide_performance_data,
        signal_cols=["alpha_a", "alpha_b"],
        regime_col="regime",
        metric_col="ic",  # Ignored for wide format
    )

    assert selector.recommend_alpha(0) == "alpha_a"
    assert selector.recommend_alpha(1) == "alpha_b"


def test_meta_selector_long_fit() -> None:
    """Verify fit and recommendation with long format data."""
    long_df = pl.DataFrame(
        {"regime": [0, 0, 1, 1], "signal_id": ["a", "b", "a", "b"], "perf": [0.1, 0.2, 0.5, 0.1]}
    )

    selector = MetaAlphaSelector()
    selector.fit(
        long_df,
        signal_cols=[],  # Ignored for long format
        regime_col="regime",
        metric_col="perf",
    )

    assert selector.recommend_alpha(0) == "b"
    assert selector.recommend_alpha(1) == "a"


def test_meta_selector_unknown_regime() -> None:
    """Verify return None for unknown regimes."""
    selector = MetaAlphaSelector()
    assert selector.recommend_alpha(99) is None


def test_meta_selector_empty_data() -> None:
    """Verify graceful handling of empty inputs."""
    selector = MetaAlphaSelector()
    selector.fit(pl.DataFrame(), ["a"], "regime", "perf")
    assert selector.recommend_alpha(0) is None
