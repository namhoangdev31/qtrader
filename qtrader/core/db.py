"""Async PostgreSQL client with read/write replica support; DuckDB client for analytics."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg
import duckdb
import polars as pl

from qtrader.core.config import settings

__all__ = ["DBClient", "DuckDBClient"]

_LOG = logging.getLogger("qtrader.core.db")


class DBClient:
    """Async PostgreSQL client with connection pooling.
    Supports separate read replica for analytics queries; falls back to write pool if no replica.
    """

    _write_pool: asyncpg.Pool | None = None
    _read_pool: asyncpg.Pool | None = None

    @classmethod
    async def get_write_pool(cls) -> asyncpg.Pool:
        """Primary DB connection pool for writes. Creates pool on first use."""
        if cls._write_pool is None:
            try:
                cls._write_pool = await asyncpg.create_pool(
                    dsn=settings.database_url,
                    min_size=2,
                    max_size=settings.database_max_connections,
                    ssl=settings.database_ssl_enabled,
                    command_timeout=60,
                )
                _LOG.info("DB write pool initialized")
            except Exception as e:
                _LOG.exception("Failed to initialize write pool: %s", e)
                raise
        return cls._write_pool

    @classmethod
    async def get_read_pool(cls) -> asyncpg.Pool:
        """Read replica connection pool. Falls back to write pool if database_read_url is not set."""
        if cls._read_pool is not None:
            return cls._read_pool
        read_url = settings.database_read_url or settings.database_url
        if read_url == settings.database_url and cls._write_pool is not None:
            return await cls.get_write_pool()
        if read_url != settings.database_url:
            try:
                cls._read_pool = await asyncpg.create_pool(
                    dsn=read_url,
                    min_size=2,
                    max_size=settings.database_max_connections,
                    ssl=settings.database_ssl_enabled,
                    command_timeout=60,
                )
                _LOG.info("DB read pool initialized (replica)")
            except Exception as e:
                _LOG.warning("Read replica pool failed, using write pool: %s", e)
                cls._read_pool = None
        if cls._read_pool is None:
            return await cls.get_write_pool()
        return cls._read_pool

    @classmethod
    async def execute(cls, query: str, *args: Any) -> str:
        """Run a write operation (INSERT, UPDATE, DELETE). Uses write pool."""
        pool = await cls.get_write_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)  # type: ignore[no-any-return]
        except asyncio.CancelledError:
            raise

    @classmethod
    async def fetch(cls, query: str, *args: Any) -> list[asyncpg.Record]:
        """Run a read query. Uses read pool when available."""
        pool = await cls.get_read_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)  # type: ignore[no-any-return]
        except asyncio.CancelledError:
            raise

    @classmethod
    async def fetchrow(cls, query: str, *args: Any) -> asyncpg.Record | None:
        """Fetch a single row. Uses read pool when available."""
        pool = await cls.get_read_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except asyncio.CancelledError:
            raise

    @classmethod
    async def fetch_as_polars(cls, query: str, *args: Any) -> pl.DataFrame:
        """Fetch rows and return as Polars DataFrame. No pandas intermediary."""
        records = await cls.fetch(query, *args)
        if not records:
            return pl.DataFrame()
        columns = list(records[0].keys())
        data: dict[str, list[Any]] = {c: [r[c] for r in records] for c in columns}
        return pl.DataFrame(data)

    @classmethod
    async def close_all(cls) -> None:
        """Close both write and read pools gracefully."""
        for name, pool in [("write", cls._write_pool), ("read", cls._read_pool)]:
            if pool is not None:
                await pool.close()
                _LOG.info("DB %s pool closed", name)
        cls._write_pool = None
        cls._read_pool = None

    @classmethod
    async def close(cls) -> None:
        """Backward compatibility: alias for close_all."""
        await cls.close_all()

    get_pool = get_write_pool


class DuckDBClient:
    """DuckDB client for analytical queries on the data lake.
    Used by AnalystSession, FeatureStore, and backtest tearsheet.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """Open a DuckDB connection. Use :memory: for ephemeral or a path for persistent DB."""
        self._con = duckdb.connect(database=db_path)

    def query(self, sql: str) -> pl.DataFrame:
        """Execute SQL and return a Polars DataFrame."""
        return self._con.execute(sql).pl()  # type: ignore[no-any-return]

    def query_parquet(self, parquet_glob: str, sql: str = "SELECT * FROM read_parquet('{glob}')") -> pl.DataFrame:
        """Query parquet files directly. Use {glob} in sql to inject parquet_glob."""
        return self._con.execute(sql.replace("{glob}", parquet_glob)).pl()  # type: ignore[no-any-return]

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()


# --- Pytest-style examples ---
# def test_duckdb_client_query_returns_polars():
#     client = DuckDBClient(":memory:")
#     df = client.query("SELECT 1 AS n")
#     assert df.shape == (1, 1) and df["n"][0] == 1
#     client.close()
# def test_duckdb_query_parquet_placeholder():
#     client = DuckDBClient(":memory:")
#     df = client.query_parquet("/fake/path/*.parquet", "SELECT 0 AS x FROM read_parquet('{glob}') LIMIT 0")
#     client.close()
