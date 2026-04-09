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
    _write_pool: asyncpg.Pool | None = None
    _read_pool: asyncpg.Pool | None = None

    @classmethod
    async def get_write_pool(cls) -> asyncpg.Pool:
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
        pool = await cls.get_write_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)
        except asyncio.CancelledError:
            raise

    @classmethod
    async def fetch(cls, query: str, *args: Any) -> list[asyncpg.Record]:
        pool = await cls.get_read_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except asyncio.CancelledError:
            raise

    @classmethod
    async def fetchrow(cls, query: str, *args: Any) -> asyncpg.Record | None:
        pool = await cls.get_read_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except asyncio.CancelledError:
            raise

    @classmethod
    async def fetch_as_polars(cls, query: str, *args: Any) -> pl.DataFrame:
        records = await cls.fetch(query, *args)
        if not records:
            return pl.DataFrame()
        columns = list(records[0].keys())
        data: dict[str, list[Any]] = {c: [r[c] for r in records] for c in columns}
        return pl.DataFrame(data)

    @classmethod
    async def close_all(cls) -> None:
        for name, pool in [("write", cls._write_pool), ("read", cls._read_pool)]:
            if pool is not None:
                await pool.close()
                _LOG.info("DB %s pool closed", name)
        cls._write_pool = None
        cls._read_pool = None

    @classmethod
    async def close(cls) -> None:
        await cls.close_all()

    get_pool = get_write_pool


class DuckDBClient:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._con = duckdb.connect(database=db_path)

    def query(self, sql: str) -> pl.DataFrame:
        return self._con.execute(sql).pl()

    def query_parquet(
        self, parquet_glob: str, sql: str = "SELECT * FROM read_parquet('{glob}')"
    ) -> pl.DataFrame:
        return self._con.execute(sql.replace("{glob}", parquet_glob)).pl()

    def close(self) -> None:
        self._con.close()
