import polars as pl
import pytest

from qtrader.verification.replay_validator import ReplayReport, ReplayValidator


def test_replay_validator_bit_perfect_pass():
    original = [
        {"timestamp": 100.0, "pnl": 50.5, "pos": {"BTC": 1.0}},
        {"timestamp": 101.0, "pnl": 60.0, "pos": {"BTC": 1.2}}
    ]
    replay = [
        {"timestamp": 100.0, "pnl": 50.5, "pos": {"BTC": 1.0}},
        {"timestamp": 101.0, "pnl": 60.0, "pos": {"BTC": 1.2}}
    ]
    
    report = ReplayValidator.compare_states(original, replay)
    assert report.status == "PASS"
    assert report.deterministic is True
    assert report.divergence_score == 0

def test_replay_validator_divergence_fail():
    original = [{"timestamp": 100.0, "pnl": 50.5}]
    # 1-bit difference in floating point at the 15th decimal place (hypothetical)
    replay = [{"timestamp": 100.0, "pnl": 50.50000000000001}]
    
    report = ReplayValidator.compare_states(original, replay)
    assert report.status == "FAIL"
    assert report.deterministic is False
    assert report.divergence_score == 1
    assert report.divergence_points[0].field == "pnl"

def test_replay_validator_polars_fidelity():
    df1 = pl.DataFrame({"a": [1, 2, 3], "b": [10.0, 20.0, 30.0]})
    df2 = pl.DataFrame({"a": [1, 2, 3], "b": [10.0, 20.0, 30.0]})
    df3 = pl.DataFrame({"a": [1, 2, 4], "b": [10.0, 20.0, 30.0]})
    
    original = [{"df": df1}]
    replay_pass = [{"df": df2}]
    replay_fail = [{"df": df3}]
    
    report_pass = ReplayValidator.compare_states(original, replay_pass)
    assert report_pass.status == "PASS"
    
    report_fail = ReplayValidator.compare_states(original, replay_fail)
    assert report_fail.status == "FAIL"

def test_replay_validator_missing_field():
    original = [{"a": 1, "b": 2}]
    replay = [{"a": 1}]
    
    report = ReplayValidator.compare_states(original, replay)
    assert report.status == "FAIL"
    assert "b" in [d.field for d in report.divergence_points]
