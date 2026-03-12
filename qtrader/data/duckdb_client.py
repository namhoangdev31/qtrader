import duckdb
import polars as pl
from pathlib import Path
from typing import Optional

class DuckDBClient:
    """Wrapper for DuckDB to query the Parquet datalake."""
    
    def __init__(self, datalake_path: str = "qtrader/data/datalake") -> None:
        self.datalake_path = Path(datalake_path)
        self.con = duckdb.connect(database=':memory:') # Or persistent file if needed

    def query(self, sql: str) -> pl.DataFrame:
        """Executes a SQL query and returns a Polars DataFrame."""
        return self.con.execute(sql).pl()

    def query_datalake(self, symbol: str, timeframe: str, filter_sql: Optional[str] = None) -> pl.DataFrame:
        """Helper to query a specific symbol/timeframe in the datalake."""
        parquet_path = self.datalake_path / f"symbol={symbol}" / f"tf={timeframe}" / "*.parquet"
        
        sql = f"SELECT * FROM read_parquet('{parquet_path}')"
        if filter_sql:
            sql += f" WHERE {filter_sql}"
            
        return self.query(sql)

    def scan_datalake(self) -> str:
        """Returns a DuckDB view or path for multi-symbol queries."""
        return str(self.datalake_path / "symbol=*" / "tf=*" / "*.parquet")
