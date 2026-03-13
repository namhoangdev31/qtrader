from pathlib import Path

import polars as pl

from qtrader.data.duckdb_client import DuckDBClient


def test_duckdb_query_datalake_parquet(tmp_path: Path) -> None:
    expected_rows = 2
    # Create partitioned parquet
    symbol = "TEST"
    timeframe = "1m"
    base = tmp_path / "datalake"
    target = base / f"symbol={symbol}" / f"tf={timeframe}"
    target.mkdir(parents=True, exist_ok=True)

    df = pl.DataFrame({"timestamp": [1, 2], "price": [10.0, 11.0]})
    df.write_parquet(target / "data.parquet")

    client = DuckDBClient(datalake_path=str(base), db_path=str(tmp_path / "db.duckdb"))
    out = client.query_datalake(symbol=symbol, timeframe=timeframe)
    assert out.shape[0] == expected_rows
    client.close()
