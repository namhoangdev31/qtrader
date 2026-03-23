import pytest
import polars as pl
from qtrader.ml.walk_forward import WalkForwardPipeline, PurgedKFoldCV

def test_walk_forward_pipeline_splits():
    df = pl.DataFrame({
        "timestamp": pl.arange(0, 100, eager=True),
        "feat": pl.arange(0, 100, eager=True)
    })
    
    # train=50, test=10, embargo=5
    wf = WalkForwardPipeline(train_size=50, test_size=10, embargo=5)
    splits = wf.get_splits(df)
    
    # Expected splits:
    # 1. start=0, train=(0,50), test=(55,65)
    # 2. start=10, train=(10,60), test=(65,75)
    # 3. start=20, train=(20,70), test=(75,85)
    # 4. start=30, train=(30,80), test=(85,95)
    # start=40: 40+50+5+10 = 105 > 100. Stop.
    
    assert len(splits) == 4
    train_0, test_0 = splits[0]
    assert train_0.height == 50
    assert test_0.height == 10
    assert train_0["timestamp"][0] == 0
    assert test_0["timestamp"][0] == 55

def test_purged_kfold_cv():
    df = pl.DataFrame({
        "timestamp": pl.arange(0, 100, eager=True),
        "feat": pl.arange(0, 100, eager=True)
    })
    
    cv = PurgedKFoldCV(n_splits=5, embargo_pct=0.05) # embargo = 5
    splits = cv.split(df, events_col="timestamp")
    
    assert len(splits) == 5
    for train, test in splits:
        assert train.height > 0
        assert test.height > 0
        # No overlap between train and test
        test_timestamps = set(test["timestamp"])
        train_timestamps = set(train["timestamp"])
        assert not (test_timestamps & train_timestamps)
