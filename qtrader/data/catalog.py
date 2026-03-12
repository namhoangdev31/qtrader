import duckdb
import polars as pl
from pathlib import Path
from datetime import datetime

class DataCatalog:
    """Manages metadata for the Data Lake partitions."""
    
    def __init__(self, db_path: str = "qtrader/data/catalog.db") -> None:
        self.con = duckdb.connect(db_path)
        self._init_table()

    def _init_table(self) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS partitions (
                symbol VARCHAR,
                timeframe VARCHAR,
                start_ts TIMESTAMP,
                end_ts TIMESTAMP,
                row_count BIGINT,
                schema_version VARCHAR,
                last_updated TIMESTAMP
            )
        """)

    def register_partition(
        self, 
        symbol: str, 
        timeframe: str, 
        df: pl.DataFrame,
        schema_version: str = "1.0.0"
    ) -> None:
        """Updates or adds partition metadata after a save operation."""
        start_ts = df["timestamp"].min() if "timestamp" in df.columns else None
        end_ts = df["timestamp"].max() if "timestamp" in df.columns else None
        row_count = len(df)
        now = datetime.now()

        # Simple Upsert
        self.con.execute("""
            DELETE FROM partitions WHERE symbol = ? AND timeframe = ?
        """, (symbol, timeframe))
        
        self.con.execute("""
            INSERT INTO partitions VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, timeframe, start_ts, end_ts, row_count, schema_version, now))

    def list_available_data(self) -> pl.DataFrame:
        """Returns all registered partitions as a Polars DataFrame."""
        return self.con.execute("SELECT * FROM partitions").pl()

    def find_partition(self, symbol: str, timeframe: str) -> Optional[dict]:
        res = self.con.execute(
            "SELECT * FROM partitions WHERE symbol = ? AND timeframe = ?", 
            (symbol, timeframe)
        ).fetchone()
        return dict(zip(["symbol", "timeframe", "start_ts", "end_ts", "rows", "version", "updated"], res)) if res else None
