import asyncpg
import logging
from typing import Optional
from qtrader.core.config import Config

class DBClient:
    """
    Asynchronous PostgreSQL client for QTrader.
    Manages connection pooling for high-performance data operations.
    """
    
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """Returns the shared connection pool, initializing it if necessary."""
        if cls._pool is None:
            try:
                cls._pool = await asyncpg.create_pool(
                    dsn=Config.DB_URL,
                    min_size=5,
                    max_size=Config.DB_MAX_CONN,
                    ssl=Config.DB_SSL
                )
                logging.info("DB | Connection pool initialized.")
            except Exception as e:
                logging.error(f"DB | Failed to initialize pool: {e}")
                raise
        return cls._pool

    @classmethod
    async def close(cls):
        """Closes the connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logging.info("DB | Connection pool closed.")

    @classmethod
    async def execute(cls, query: str, *args):
        """Executes a command (INSERT, UPDATE, DELETE)."""
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def fetch(cls, query: str, *args):
        """Fetches multiple rows."""
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def fetchrow(cls, query: str, *args):
        """Fetches a single row."""
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
