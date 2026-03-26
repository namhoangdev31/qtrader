from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import duckdb
import polars as pl

from qtrader.core.events import BaseEvent

logger = logging.getLogger(__name__)


class AuditStore:
    """
    Principal Analytical Audit Store (OLAP).
    
    Provides specialized columnar storage for system events using DuckDB. 
    Ideal for regulatory compliance, TCA, and large-scale historical 
    research without impacting operational transaction throughput.
    
    Architecture:
    - **DuckDB Core**: Columnar storage for sub-100ms aggregation.
    - **Polars Interop**: Direct SQL-to-Polars transformation for quants.
    - **Separation of Concern**: Secondary to EventStore, decoupled via EventBus.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialize the analytical audit store.
        
        Args:
            db_path: Path to the DuckDB file (use ':memory:' for transient sessions).
        """
        self._db_path = db_path
        self._conn = duckdb.connect(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Execute the analytical schema definition."""
        try:
            schema_file = os.path.join(os.path.dirname(__file__), "audit_schema.sql")
            with open(schema_file, "r") as f:
                self._conn.execute(f.read())
            logger.info(f"AUDIT_STORE_READY | Path: {self._db_path}")
        except Exception as e:
            logger.critical(f"AUDIT_SCHEMA_ERROR | Could not initialize DuckDB: {e!s}")
            raise

    async def append(self, event: BaseEvent) -> bool:
        """
        Append a system event to the analytical store.
        
        Events are flattened into a columnar format with JSON-backed payloads 
        to enable structured SQL querying of nested fields.
        
        Args:
            event: The immutable event to index.
            
        Returns:
            bool: True if ingestion was successful.
        """
        try:
            # Flatten event payload into JSON string for DuckDB storage
            # We dump the entire payload model for depth preservation
            # Using Pydantic's efficient JSON serializer
            payload_str = event.model_dump_json(include={"payload"})
            
            # Standard Parameterized SQL for SQL injection safety
            self._conn.execute(
                """
                INSERT INTO audit_events 
                (event_id, trace_id, event_type, timestamp_us, source, payload_json) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    str(event.trace_id),
                    event.event_type.value,
                    event.timestamp,
                    event.source,
                    payload_str
                )
            )
            return True
            
        except Exception as e:
            logger.error(f"AUDIT_APPEND_FAILURE | Event {event.event_id} | Error: {e!s}")
            # In a production system, we would buffer or emit an AuditErrorEvent
            return False

    def query_olap(self, sql: str) -> pl.DataFrame:
        """
        Execute high-performance analytical SQL against the columnar store.
        
        Returns results as a Polars DataFrame for efficient vectorized 
        analysis (TCA, Risk Attribution, etc.).
        
        Args:
            sql: The DuckDB-compatible SQL query.
            
        Returns:
            pl.DataFrame: The materialized query result.
        """
        try:
            # Materialize directly from DuckDB result to Polars zero-copy
            return self._conn.execute(sql).pl()
        except Exception as e:
            logger.error(f"AUDIT_QUERY_ERROR | SQL: {sql} | Error: {e!s}")
            return pl.DataFrame()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.info("AUDIT_STORE_HALTED | Storage layer detached.")
