import logging
from datetime import datetime

import polars as pl

from qtrader.core.db import DBClient


class DataCatalog:
    """
    Manages metadata for the Data Lake partitions using PostgreSQL.
    Tracks symbols, timeframes, and data ranges in the institutional database.
    """
    
    def __init__(self) -> None:
        # Table initialization will be handled lazily or via migration
        pass

    async def initialize(self) -> None:
        """Creates the necessary schema if it doesn't exist."""
        query = """
        CREATE TABLE IF NOT EXISTS data_partitions (
            symbol VARCHAR(20),
            timeframe VARCHAR(10),
            start_ts TIMESTAMP,
            end_ts TIMESTAMP,
            row_count BIGINT,
            schema_version VARCHAR(10),
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, timeframe)
        );
        """
        await DBClient.execute(query)
        logging.info("CATALOG | PostgreSQL schema verified.")

    async def register_partition(
        self, 
        symbol: str, 
        timeframe: str, 
        df: pl.DataFrame,
        schema_version: str = "1.0.0"
    ) -> None:
        """Registers or updates a data partition in the PostgreSQL catalog."""
        start_ts = df["timestamp"].min() if "timestamp" in df.columns else None
        end_ts = df["timestamp"].max() if "timestamp" in df.columns else None
        row_count = len(df)
        
        query = """
        INSERT INTO data_partitions (symbol, timeframe, start_ts, end_ts, row_count, schema_version, last_updated)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (symbol, timeframe) DO UPDATE SET
            start_ts = EXCLUDED.start_ts,
            end_ts = EXCLUDED.end_ts,
            row_count = EXCLUDED.row_count,
            last_updated = EXCLUDED.last_updated;
        """
        await DBClient.execute(
            query,
            symbol,
            timeframe,
            start_ts.to_datetime() if hasattr(start_ts, "to_datetime") else start_ts,
            end_ts.to_datetime() if hasattr(end_ts, "to_datetime") else end_ts,
            row_count,
            schema_version,
            datetime.now(),
        )

    async def list_available_data(self) -> pl.DataFrame:
        """Returns all registered partitions from PostgreSQL."""
        rows = await DBClient.fetch("SELECT * FROM data_partitions")
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame([dict(r) for r in rows])

    async def find_partition(self, symbol: str, timeframe: str) -> dict | None:
        """Finds metadata for a specific partition."""
        row = await DBClient.fetchrow(
            "SELECT * FROM data_partitions WHERE symbol = $1 AND timeframe = $2",
            symbol,
            timeframe,
        )
        return dict(row) if row else None
