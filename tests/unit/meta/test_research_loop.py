import polars as pl

from qtrader.meta.research_loop import ResearchLoop

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

RAW_DATA = pl.DataFrame(
    {
        "timestamp": [1, 2, 3, 4, 5],
        "close": [100.0, 101.0, 102.0, 101.5, 103.0],
        "volume": [1000, 1200, 1500, 1100, 1300],
    }
)


def test_research_loop_data_ingestion() -> None:
    """Verify that data is cleaned and standardized."""
    loop = ResearchLoop()
    data_with_null = pl.DataFrame({"a": [1, None, 2]})
    cleaned = loop.ingest_data(data_with_null)
    # 2 rows remain
    expected_len = 2
    assert len(cleaned) == expected_len


def test_research_loop_feature_generation() -> None:
    """Verify that returns and features are correctly computed."""
    loop = ResearchLoop()
    features = loop.generate_features(RAW_DATA)
    # Check if extra columns are added (returns, log_volume)
    assert "returns" in features.columns
    assert "log_volume" in features.columns


def test_research_loop_validation_logic() -> None:
    """Verify quality filtering for model deployment."""
    # Min Sharpe = 2.0
    loop = ResearchLoop(config={"min_sharpe": 2.0})

    # CASE 1: Pass
    metrics_good = {"sharpe": 2.5}
    assert loop.validate_model(metrics_good) is True

    # CASE 2: Fail
    metrics_bad = {"sharpe": 1.5}
    assert loop.validate_model(metrics_bad) is False


def test_research_loop_full_iteration() -> None:
    """Verify successful end-to-end iteration of the research loop."""
    loop = ResearchLoop(config={"min_sharpe": 1.5})
    result = loop.run_iteration(RAW_DATA)

    assert result["status"] == "DEPLOYED"
    assert "metrics" in result
    expected_size = 5
    assert result["sample_size"] == expected_size


def test_research_loop_empty_protection() -> None:
    """Verify robustness to empty data input."""
    loop = ResearchLoop()
    empty = pl.DataFrame()
    result = loop.run_iteration(empty)
    assert result["status"] == "FAILED"
    assert "reason" in result
