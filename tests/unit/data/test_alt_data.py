from datetime import datetime, timedelta

import polars as pl

from qtrader.data.alt_data import AltDataProcessor

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

START_TIME = datetime(2025, 1, 1, 10, 0, 0)
TIMES = [START_TIME + timedelta(minutes=i) for i in range(10)]

MAIN_FEATURES = pl.DataFrame(
    {
        "timestamp": TIMES,
        "close": [100.0 + i for i in range(10)],
    }
)

ALT_FEED_1 = pl.DataFrame(
    {
        "timestamp": [TIMES[2], TIMES[5], TIMES[8]],
        "sentiment": [0.5, -0.2, 0.8],
    }
)

ALT_FEED_2 = pl.DataFrame(
    {
        "timestamp": [TIMES[0], TIMES[5]],
        "anomaly_score": [0.1, 0.9],
    }
)


def test_alt_data_align_and_merge() -> None:
    """Verify that alt-data is left-joined and padded correctly."""
    processor = AltDataProcessor()
    merged = processor.align_and_merge(MAIN_FEATURES, ALT_FEED_1)

    # Initial length must be preserved (10 rows)
    expected_rows = 10
    assert merged.height == expected_rows

    # Check specific values from ALT_FEED_1
    val_2 = 0.5
    val_5 = -0.2
    val_8 = 0.8
    assert merged["sentiment"][2] == val_2
    assert merged["sentiment"][5] == val_5
    assert merged["sentiment"][8] == val_8

    # All others should be fill_null(0.0)
    neutral = 0.0
    assert merged["sentiment"][0] == neutral
    assert merged["sentiment"][1] == neutral


def test_alt_data_normalize_signals() -> None:
    """Verify that normalization (z-score) is applied correctly."""
    # Data: [1.0, 2.0, 3.0] -> Mean = 2.0, Std = 1.0 (sample)
    # Z-scores: [(1-2)/1, (2-2)/1, (3-2)/1] = [-1.0, 0.0, 1.0]
    raw_vals = [1.0, 2.0, 3.0]
    expected_z = [-1.0, 0.0, 1.0]
    raw_df = pl.DataFrame({"score": raw_vals})
    processor = AltDataProcessor()

    normalized = processor.normalize_signals(raw_df, ["score"])
    z_scores = normalized["score_z"].to_list()

    assert z_scores == expected_z


def test_alt_data_pipeline_multiple_sources() -> None:
    """Verify the pipeline with multiple external sources."""
    processor = AltDataProcessor()
    external = [ALT_FEED_1, ALT_FEED_2]

    final = processor.process_pipeline(MAIN_FEATURES, external)

    # Verify all alt-columns present
    assert "sentiment" in final.columns
    assert "anomaly_score" in final.columns
    # Verify normalized variants present
    assert "sentiment_z" in final.columns
    assert "anomaly_score_z" in final.columns

    # Check total row count
    assert final.height == MAIN_FEATURES.height


def test_alt_data_empty_input_protection() -> None:
    """Ensure edge cases (empty data) are handled without crashing."""
    processor = AltDataProcessor()
    empty = pl.DataFrame()

    # 1. Empty main features: should return empty
    res1 = processor.align_and_merge(empty, ALT_FEED_1)
    assert res1.is_empty()

    # 2. Empty alt feed: should return main unchanged
    res2 = processor.align_and_merge(MAIN_FEATURES, empty)
    assert res2.height == MAIN_FEATURES.height
    assert "timestamp" in res2.columns

    # 3. Pipeline with no sources: should return main unchanged
    res3 = processor.process_pipeline(MAIN_FEATURES, [])
    assert res3.equals(MAIN_FEATURES)
