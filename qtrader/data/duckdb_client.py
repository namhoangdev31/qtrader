from pathlib import Path

import duckdb
import polars as pl

from qtrader.core.config import Config


class DuckDBClient:
    """Wrapper for DuckDB to query the Parquet datalake."""
    
    def __init__(self, datalake_path: str | None = None, db_path: str | None = None) -> None:
        self.datalake_path = Path(datalake_path or Config.DATALAKE_URI)
        self.con = duckdb.connect(database=db_path or Config.DB_PATH) 

    def query(self, sql: str) -> pl.DataFrame:
        """Executes a SQL query and returns a Polars DataFrame."""
        return self.con.execute(sql).pl()

    def query_datalake(self, symbol: str, timeframe: str, filter_sql: str | None = None) -> pl.DataFrame:
        """Helper to query a specific symbol/timeframe in the datalake."""
        parquet_path = self.datalake_path / f"symbol={symbol}" / f"tf={timeframe}" / "*.parquet"

        if not parquet_path.parent.exists():
            raise FileNotFoundError(f"No datalake partition for {symbol} {timeframe} at {parquet_path.parent}")
        
        sql = f"SELECT * FROM read_parquet('{parquet_path}')"
        if filter_sql:
            sql += f" WHERE {filter_sql}"
            
        return self.query(sql)

    def scan_datalake(self) -> str:
        """Returns a DuckDB view or path for multi-symbol queries."""
        return str(self.datalake_path / "symbol=*" / "tf=*" / "*.parquet")

    def close(self) -> None:
        self.con.close()
