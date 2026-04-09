import polars as pl
import pytest
from qtrader.ml.walk_forward import PurgedKFoldCV, WalkForwardPipeline


def test_walk_forward_pipeline_splits():
    df = pl.DataFrame(
        {"timestamp": pl.arange(0, 100, eager=True), "feat": pl.arange(0, 100, eager=True)}
    )
    wf = WalkForwardPipeline(train_size=50, test_size=10, embargo=5)
    splits = wf.get_splits(df)
    assert len(splits) == 4
    (train_0, test_0) = splits[0]
    assert train_0.height == 50
    assert test_0.height == 10
    assert train_0["timestamp"][0] == 0
    assert test_0["timestamp"][0] == 55


def test_purged_kfold_cv():
    df = pl.DataFrame(
        {"timestamp": pl.arange(0, 100, eager=True), "feat": pl.arange(0, 100, eager=True)}
    )
    cv = PurgedKFoldCV(n_splits=5, embargo_pct=0.05)
    splits = cv.split(df, events_col="timestamp")
    assert len(splits) == 5
    for train, test in splits:
        assert train.height > 0
        assert test.height > 0
        test_timestamps = set(test["timestamp"])
        train_timestamps = set(train["timestamp"])
        assert not test_timestamps & train_timestamps
