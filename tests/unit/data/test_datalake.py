import os
import tempfile
from pathlib import Path
import polars as pl
import pytest
from qtrader.data.datalake import DataLake
from datetime import datetime


@pytest.fixture
def temp_datalake():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield DataLake(base_path=tmpdir)

def test_datalake_save_load(temp_datalake):

    df = pl.DataFrame(
        {
            "timestamp": pl.datetime_range(
                datetime(2023, 1, 1), datetime(2023, 1, 1, 4), interval="1h", eager=True
            ),
            "open": [100.0] * 5,
            "high": [105.0] * 5,
            "low": [95.0] * 5,
            "close": [102.0] * 5,
            "volume": [1000.0] * 5,
        }
    )
    symbol = "BTC_USDT"
    timeframe = "1h"
    temp_datalake.save_data(df, symbol, timeframe)
    path = temp_datalake._get_path(symbol, timeframe)
    assert path.exists()
    loaded_df = temp_datalake.load_data(symbol, timeframe)
    assert loaded_df.height == 5
    assert "close" in loaded_df.columns

def test_datalake_list_symbols(temp_datalake):
    df = pl.DataFrame({"a": [1]})
    temp_datalake.save_data(df, "BTC_USDT", "1h")
    temp_datalake.save_data(df, "ETH_USDT", "1h")
    symbols = [d.name.split("=")[1] for d in temp_datalake.base_path.iterdir() if d.is_dir()]
    assert "BTC_USDT" in symbols
    assert "ETH_USDT" in symbols