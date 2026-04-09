import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import polars as pl

from qtrader.core.config import Config

logger = logging.getLogger(__name__)


class DuckDBClient:
    def __init__(
        self,
        datalake_path: str | None = None,
        db_path: str | None = None,
        enable_cache: bool = True,
        max_cache_size: int = 128,
        max_workers: int = 8,
        memory_limit_mb: int | None = None,
    ) -> None:
        self.datalake_path = Path(datalake_path or Config.DATALAKE_URI)
        self.con = duckdb.connect(database=db_path or Config.DB_PATH)
        self._configure_duckdb(memory_limit_mb)
        self.enable_cache = enable_cache
        if enable_cache:
            self.query_cache = lru_cache(maxsize=max_cache_size)
        self.max_workers = min(max_workers, duckdb.default_thread_amount() or 8)
        self._query_patterns: dict[str, str] = {}
        self._compiled_queries: dict[str, duckdb.Result] = {}

    def _configure_duckdb(self, memory_limit_mb: int | None = None) -> None:
        self.con.execute("SET enable_progress_bar = FALSE")
        import os

        num_threads = os.cpu_count() or 4
        self.con.execute(f"SET threads = {num_threads}")
        self.con.execute("SET enable_parallel = true")
        self.con.execute("SET enable_vectorized_execution = true")
        self.con.execute("SET metadata_cache_size = '512MB'")
        if memory_limit_mb is None:
            memory_limit = num_threads * 512
        else:
            memory_limit = memory_limit_mb * num_threads
        self.con.execute(f"SET memory_limit = '{memory_limit}MB'")
        self.con.execute("SET enable_union_reorder = true")
        self.con.execute("SET enable_cache = true")
        self.con.execute(f"SET cache_size = '{min(4096, memory_limit // 2)}MB'")
        self.con.execute("SET default_order = 'true'")
        self.con.execute("SET enable_profiling = 'off'")
        self.con.execute("SET enable_pushdown_predicates = true")
        self.con.execute("SET enable_pushdown_projections = true")
        self.con.execute("SET enforce_strict_order = false")

    def query(self, sql: str) -> pl.DataFrame:
        return self.con.execute(sql).pl()

    def query_optimized(self, sql: str) -> pl.DataFrame:
        if "*" in sql.upper():
            sql = self._project_columns(sql)
        return self.con.execute(sql).pl()

    def _project_columns(self, sql: str) -> str:
        common_columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vwap",
            "bid",
            "ask",
            "bid_size",
            "ask_size",
        ]
        if "SELECT *" in sql.upper():
            col_list = ", ".join(common_columns)
            return sql.replace("SELECT *", f"SELECT {col_list}")
        return sql

    def query_datalake(
        self,
        symbol: str,
        timeframe: str,
        filter_sql: str | None = None,
        columns: list[str] | None = None,
        use_cache: bool = True,
        parallel: bool = True,
    ) -> pl.DataFrame:
        parquet_path = self.datalake_path / f"symbol={symbol}" / f"tf={timeframe}" / "*.parquet"
        if not parquet_path.parent.exists():
            raise FileNotFoundError(
                f"No datalake partition for {symbol} {timeframe} at {parquet_path.parent}"
            )
        read_query = f"SELECT * FROM read_parquet('{parquet_path}', union_by_name=true)"
        if columns:
            col_list = ", ".join(f"'{col}'" for col in columns)
            read_query = (
                f"SELECT {col_list} FROM read_parquet('{parquet_path}', union_by_name=true)"
            )
        sql = read_query
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        if parallel:
            sql = f"EXPLAIN PARALLEL {sql}"
        return self.query_optimized(sql)

    def query_with_projection(
        self, symbol: str, timeframe: str, columns: list[str], filter_sql: str | None = None
    ) -> pl.DataFrame:
        parquet_path = self.datalake_path / f"symbol={symbol}" / f"tf={timeframe}" / "*.parquet"
        if not parquet_path.parent.exists():
            raise FileNotFoundError(
                f"No datalake partition for {symbol} {timeframe} at {parquet_path.parent}"
            )
        col_list = ", ".join(f"'{col}'" for col in columns)
        sql = f"SELECT {col_list} FROM read_parquet('{parquet_path}', union_by_name=true, compression='snappy', hive_partitioning=1)"
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        return self.query_optimized(sql)

    def scan_datalake(self) -> str:
        return str(self.datalake_path / "symbol=*" / "tf=*" / "*.parquet")

    def query_batch(
        self, queries: list[tuple[str, list[str], str | None]], parallel: bool = True
    ) -> list[pl.DataFrame]:
        if not parallel:
            return [self.query_datalake(*q) for q in queries]
        results = [None] * len(queries)

        def query_single(idx: int, args: tuple[str, list[str], str | None]) -> None:
            (symbol, timeframe, columns, filter_sql) = args
            results[idx] = self.query_datalake(symbol, timeframe, filter_sql, columns)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(query_single, i, q): i for (i, q) in enumerate(queries)}
            for _future in as_completed(futures):
                pass
        return results

    def query_multi_symbol(
        self,
        symbols: list[str],
        timeframe: str,
        columns: list[str] | None = None,
        filter_sql: str | None = None,
        parallel: bool = True,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        parquet_path_pattern = str(
            self.datalake_path / "symbol=*" / f"tf={timeframe}" / "*.parquet"
        )
        if columns:
            col_list = ", ".join(f"'{col}'" for col in columns)
            sql = (
                f"SELECT {col_list} FROM read_parquet('{parquet_path_pattern}', union_by_name=true)"
            )
        else:
            sql = f"SELECT * FROM read_parquet('{parquet_path_pattern}', union_by_name=true)"
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        return self.query_optimized(sql)

    def create_composite_indexes(self) -> None:
        self.con.execute(
            "\n            CREATE INDEX IF NOT EXISTS idx_symbol_timeframe\n            ON data_partitions (symbol, timeframe)\n        "
        )
        self.con.execute(
            "\n            CREATE INDEX IF NOT EXISTS idx_start_ts\n            ON data_partitions (start_ts DESC)\n        "
        )
        self.con.execute(
            "\n            CREATE INDEX IF NOT EXISTS idx_symbol_timestamp\n            ON data_partitions (symbol, timestamp DESC)\n        "
        )

    def create_index(self, table_name: str, columns: list[str]) -> None:
        col_list = ", ".join(columns)
        self.con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name} ON {table_name} ({col_list})"
        )

    def optimize_parquet_files(self) -> None:
        try:
            self.con.execute("CALL optimize_parquet_files()")
            logger.info("Optimized all Parquet files in datalake")
        except Exception as e:
            logger.warning(f"Could not optimize Parquet files: {e}")

    def create_materialized_view(self, view_name: str, sql: str) -> None:
        self.con.execute(
            f"\n            CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name}\n            AS {sql}\n        "
        )

    def refresh_materialized_view(self, view_name: str) -> None:
        self.con.execute(f"\n            REFRESH MATERIALIZED VIEW {view_name}\n        ")

    def close(self) -> None:
        self.con.close()
        if hasattr(self, "query_cache"):
            self.query_cache.cache_clear()
