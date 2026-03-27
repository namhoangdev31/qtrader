import polars as pl
import pytest

from qtrader.meta.governance_engine import MetaGovernanceEngine, StrategyCandidate


@pytest.fixture
def engine() -> MetaGovernanceEngine:
    """Initialize MetaGovernanceEngine with industrial curation defaults."""
    return MetaGovernanceEngine(
        max_daily_quota=3, min_sharpe_threshold=1.5, max_correlation_threshold=0.5
    )


def test_meta_governance_ranking_priority(engine: MetaGovernanceEngine) -> None:
    """Verify that strategies are prioritized by Sharpe ratio."""
    # S1: Sharpe 2.0
    # S2: Sharpe 1.8
    # S3: Sharpe 1.0 (fails pre-filter)
    s1 = StrategyCandidate("S1", "x+y", pl.Series([1.0, 0.0, 0.0]), 2.0)
    s2 = StrategyCandidate("S2", "x*z", pl.Series([0.0, 1.0, 0.0]), 1.8)
    s3 = StrategyCandidate("S3", "x-y", pl.Series([0.0, 0.0, 1.0]), 1.0)

    pool = [s1, s2, s3]
    curated = engine.curate(pool)

    assert len(curated) == 2  # noqa: S101, PLR2004
    assert curated[0].strategy_id == "S1"  # noqa: S101
    assert curated[1].strategy_id == "S2"  # noqa: S101


def test_meta_governance_correlation_diversity(engine: MetaGovernanceEngine) -> None:
    """Verify that redundant (highly correlated) strategies are rejected."""
    # S1: Base strategy (Sharpe 2.0)
    # S2: Highly correlated with S1 (Sharpe 1.9, corr=1.0)
    s1 = StrategyCandidate("S1", "x+y", pl.Series([1.0, 2.0, 3.0]), 2.0)
    s2 = StrategyCandidate("S2", "x+y+0.01", pl.Series([1.0, 2.0, 3.0]), 1.9)

    pool = [s1, s2]
    curated = engine.curate(pool)

    assert len(curated) == 1  # noqa: S101
    assert curated[0].strategy_id == "S1"  # noqa: S101


def test_meta_governance_daily_quota(engine: MetaGovernanceEngine) -> None:
    """Verify that the curated set size does not exceed the daily quota."""
    # 5 high-quality, uncorrelated strategies (one-hot columns)
    pool = [
        StrategyCandidate(
            f"S{i}", str(i), pl.Series([1.0 if j == i else 0.0 for j in range(5)]), 2.0
        )
        for i in range(5)
    ]

    curated = engine.curate(pool)
    assert len(curated) == 3  # noqa: S101, PLR2004


def test_meta_governance_empty_pool(engine: MetaGovernanceEngine) -> None:
    """Verify that an empty pool results in an empty curated set."""
    assert not engine.curate([])  # noqa: S101


def test_meta_governance_single_member_stats(engine: MetaGovernanceEngine) -> None:
    """Verify statistics for a single-member set."""
    s1 = StrategyCandidate("S1", "x", pl.Series([1.0, 2.0]), 2.0)
    curated = engine.curate([s1])
    assert len(curated) == 1  # noqa: S101
    assert engine.get_governance_report()["mean_diversity_score"] == 0.0  # noqa: S101
