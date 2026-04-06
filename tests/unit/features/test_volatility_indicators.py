import pytest
import polars as pl
from qtrader.features.technical.volatility import ATRFeature

def test_atr_calculation():
    # 1. Create dummy data (Price stable then jumps)
    # TR = max(H-L, abs(H-Cp), abs(L-Cp))
    data = pl.DataFrame({
        "high": [100, 102, 104, 106, 108, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200],
        "low":  [98,  100, 102, 104, 106, 108, 115, 125, 135, 145, 155, 165, 175, 185, 195],
        "close": [99,  101, 103, 105, 107, 109, 118, 128, 138, 148, 158, 168, 178, 188, 198]
    })
    
    atr_window = 5
    indicator = ATRFeature(window=atr_window)
    
    # 2. Compute
    result = indicator.compute(data)
    
    # 3. Assertions
    assert len(result) == len(data)
    assert result.name == "atr"
    # First (window-1) should be null
    assert result[:atr_window-1].is_null().all()
    # After window, should have values
    assert not result[atr_window:].is_null().any()
    
    # Check trend: Price jumps significantly at index 6, ATR should rise
    assert result[14] > result[5]

def test_atr_missing_cols():
    indicator = ATRFeature()
    with pytest.raises(ValueError, match="Missing required columns"):
        indicator.compute(pl.DataFrame({"close": [1, 2, 3]}))
