from datetime import datetime

import polars as pl
import pytest

from qtrader.alpha.registry import AlphaEngine
from qtrader.alpha.technical import MomentumAlpha


def test_alpha_engine_initialization():
    engine = AlphaEngine(alpha_names=["momentum", "mean_reversion"])
    assert "momentum" in engine._alphas
    assert "mean_reversion" in engine._alphas
    assert len(engine._alphas) == 2

def test_alpha_engine_compute_all():
    df = pl.DataFrame({
        "timestamp": pl.datetime_range(datetime(2023, 1, 1, 0), datetime(2023, 1, 1, 4), interval="1h", eager=True),
        "symbol": ["AAPL"] * 5,
        "close": [100.0, 101.0, 102.0, 101.5, 103.0],
        "open": [100.0] * 5,
        "high": [105.0] * 5,
        "low": [95.0] * 5,
        "volume": [1000.0] * 5
    })
    
    engine = AlphaEngine(alpha_names=["momentum"])
    out = engine.compute_all(df)
    
    assert "momentum" in out.columns
    assert "composite_alpha" in out.columns
    assert out.height == 5

def test_alpha_engine_weights():
    engine = AlphaEngine(alpha_names=["momentum", "mean_reversion"])
    # Default weights should be equal
    weights = engine._compute_weights()
    assert weights["momentum"] == 0.5
    assert weights["mean_reversion"] == 0.5
    
    # Update IC and check weights
    engine._ic["momentum"] = 0.6
    engine._ic["mean_reversion"] = 0.2
    weights = engine._compute_weights()
    assert weights["momentum"] == pytest.approx(0.75)
    assert weights["mean_reversion"] == pytest.approx(0.25)
