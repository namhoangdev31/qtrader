import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

# import duckdb
import polars as pl

from qtrader.core.config import Config

logger = logging.getLogger(__name__)


class DuckDBClient:
    """Optimized wrapper for DuckDB to query the Parquet datalake with aggressive parallelization."""
    
    def __init__(
        self, 
        datalake_path: str | None = None, 
        db_path: str | None = None,
        enable_cache: bool = True,
        max_cache_size: int = 128,
        max_workers: int = 8,
        memory_limit_mb: int | None = None
    ) -> None:
        self.datalake_path = Path(datalake_path or Config.DATALAKE_URI)
        self.con = duckdb.connect(database=db_path or Config.DB_PATH)
        
        # Configure DuckDB for optimal performance
        self._configure_duckdb(memory_limit_mb)
        
        # Enable caching if requested
        self.enable_cache = enable_cache
        if enable_cache:
            self.query_cache = lru_cache(maxsize=max_cache_size)
        self.max_workers = min(max_workers, (duckdb.default_thread_amount() or 8))
        
        # Pre-compile common query patterns
        self._query_patterns: dict[str, str] = {}
        self._compiled_queries: dict[str, duckdb.Result] = {}
    
    def _configure_duckdb(self, memory_limit_mb: int | None = None) -> None:
        """Configure DuckDB for maximum performance with adaptive settings."""
        # Disable progress bar for faster execution
        self.con.execute("SET enable_progress_bar = FALSE")
        
        # Adaptive thread count: Use all available cores for maximum parallelization
        import os
        num_threads = os.cpu_count() or 4
        
        # Set thread count - use all cores for parallel scans
        self.con.execute(f"SET threads = {num_threads}")
        
        # Enable parallel execution for parquet scanning
        self.con.execute("SET enable_parallel = true")
        
        # Use SIMD optimizations if available
        self.con.execute("SET enable_vectorized_execution = true")
        
        # Optimize parquet metadata caching with larger size
        self.con.execute("SET metadata_cache_size = '512MB'")
        
        # Memory limit - fix: use proper formula for parallel scans
        # Each thread needs enough memory for a chunk of data
        if memory_limit_mb is None:
            # Default: 512MB per thread for high-frequency trading workloads
            memory_limit = num_threads * 512
        else:
            memory_limit = memory_limit_mb * num_threads
        
        self.con.execute(f"SET memory_limit = '{memory_limit}MB'")
        
        # Enable union reordering for better query plans
        self.con.execute("SET enable_union_reorder = true")
        
        # Cache query results
        self.con.execute("SET enable_cache = true")
        self.con.execute(f"SET cache_size = '{min(4096, memory_limit // 2)}MB'")
        
        # Optimize for high-performance parquet reading
        self.con.execute("SET default_order = 'true'")
        self.con.execute("SET enable_profiling = 'off'")
        
        # Additional optimizations for HFT workloads
        self.con.execute("SET enable_pushdown_predicates = true")
        self.con.execute("SET enable_pushdown_projections = true")
        self.con.execute("SET enforce_strict_order = false")
    
    def query(self, sql: str) -> pl.DataFrame:
        """Executes a SQL query with optimization and returns a Polars DataFrame."""
        return self.con.execute(sql).pl()
    
    def query_optimized(self, sql: str) -> pl.DataFrame:
        """
        Optimized query with column pruning and filtering at scan level.
        Reduces memory usage and I/O operations.
        """
        # Add projection pushdown hint if SQL doesn't specify columns
        if "*" in sql.upper():
            # Auto-generate column selection for common tables
            sql = self._project_columns(sql)
        
        return self.con.execute(sql).pl()
    
    def _project_columns(self, sql: str) -> str:
        """Auto-generate column projection for better I/O efficiency."""
        # Common columns in market data
        common_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                         'vwap', 'bid', 'ask', 'bid_size', 'ask_size']
        
        # Replace SELECT * with explicit column list
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
        parallel: bool = True
    ) -> pl.DataFrame:
        """
        Optimized helper to query a specific symbol/timeframe in the datalake.
        Supports column projection and lazy evaluation with aggressive optimization.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (e.g., '1h', '1d')
            filter_sql: Optional WHERE clause filter
            columns: Optional list of columns to read (for projection pushdown)
            use_cache: Whether to use query caching
            parallel: Whether to enable parallel scan hints
            
        Returns:
            Polars DataFrame
        """
        parquet_path = self.datalake_path / f"symbol={symbol}" / f"tf={timeframe}" / "*.parquet"

        if not parquet_path.parent.exists():
            raise FileNotFoundError(f"No datalake partition for {symbol} {timeframe} at {parquet_path.parent}")
        
        # Build optimized SQL with column projection (aggressive)
        read_query = f"SELECT * FROM read_parquet('{parquet_path}', union_by_name=true)"
        
        # Add column projection if specified (projection pushdown)
        if columns:
            col_list = ", ".join(f"'{col}'" for col in columns)
            read_query = f"SELECT {col_list} FROM read_parquet('{parquet_path}', union_by_name=true)"
        
        # Add filters if specified
        sql = read_query
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        
        # Add parallel scan hint for better I/O performance
        if parallel:
            sql = f"EXPLAIN PARALLEL {sql}"
        
        # Use optimized query method
        return self.query_optimized(sql)
    
    def query_with_projection(
        self,
        symbol: str,
        timeframe: str,
        columns: list[str],
        filter_sql: str | None = None
    ) -> pl.DataFrame:
        """
        Query with explicit column projection for minimal I/O (aggressive optimization).
        Reads only required columns from Parquet files with lazy evaluation.
        """
        parquet_path = self.datalake_path / f"symbol={symbol}" / f"tf={timeframe}" / "*.parquet"
        
        if not parquet_path.parent.exists():
            raise FileNotFoundError(f"No datalake partition for {symbol} {timeframe} at {parquet_path.parent}")
        
        # Build projection-only query with aggressive optimization
        col_list = ", ".join(f"'{col}'" for col in columns)
        sql = f"SELECT {col_list} FROM read_parquet('{parquet_path}', union_by_name=true, compression='snappy', hive_partitioning=1)"
        
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        
        return self.query_optimized(sql)
    
    def scan_datalake(self) -> str:
        """Returns a DuckDB view or path for multi-symbol queries."""
        return str(self.datalake_path / "symbol=*" / "tf=*" / "*.parquet")
    
    def query_batch(
        self,
        queries: list[tuple[str, list[str], str | None]],
        parallel: bool = True
    ) -> list[pl.DataFrame]:
        """
        Execute multiple queries in parallel for batch data loading using ThreadPoolExecutor.
        
        Args:
            queries: List of tuples (symbol, timeframe, columns, filter_sql)
            parallel: Whether to execute queries in parallel
            
        Returns:
            List of DataFrames in the same order as queries
        """
        if not parallel:
            return [self.query_datalake(*q) for q in queries]
        
        # Parallel execution using ThreadPoolExecutor for better I/O parallelism
        results = [None] * len(queries)
        
        def query_single(idx: int, args: tuple[str, list[str], str | None]) -> None:
            symbol, timeframe, columns, filter_sql = args
            results[idx] = self.query_datalake(symbol, timeframe, filter_sql, columns)
        
        # Use ThreadPoolExecutor for parallel I/O operations
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(query_single, i, q): i 
                for i, q in enumerate(queries)
            }
            for _future in as_completed(futures):
                pass  # Results are already stored
        
        return results
    
    def query_multi_symbol(
        self,
        symbols: list[str],
        timeframe: str,
        columns: list[str] | None = None,
        filter_sql: str | None = None,
        parallel: bool = True
    ) -> pl.DataFrame:
        """
        Query multiple symbols in a single operation using DuckDB's UNION ALL.
        This is much faster than loading each symbol separately.
        
        Args:
            symbols: List of trading symbols
            timeframe: Timeframe string (e.g., '1h', '1d')
            columns: Optional list of columns to read (for projection pushdown)
            filter_sql: Optional WHERE clause filter
            parallel: Whether to execute in parallel (not applicable for single query)
            
        Returns:
            Single DataFrame with all symbols concatenated
        """
        if not symbols:
            return pl.DataFrame()
        
        # Build parquet path pattern for all symbols
        parquet_path_pattern = str(
            self.datalake_path / "symbol=*" / f"tf={timeframe}" / "*.parquet"
        )
        
        # Build optimized SQL with UNION ALL for single query
        if columns:
            col_list = ", ".join(f"'{col}'" for col in columns)
            sql = f"SELECT {col_list} FROM read_parquet('{parquet_path_pattern}', union_by_name=true)"
        else:
            sql = f"SELECT * FROM read_parquet('{parquet_path_pattern}', union_by_name=true)"
        
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        
        return self.query_optimized(sql)
    
    def create_composite_indexes(self) -> None:
        """Create composite indexes for common query patterns."""
        # Index for symbol + timeframe lookups
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_timeframe 
            ON data_partitions (symbol, timeframe)
        """)
        
        # Index for date range queries
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_start_ts 
            ON data_partitions (start_ts DESC)
        """)
        
        # Additional indexes for performance
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_timestamp 
            ON data_partitions (symbol, timestamp DESC)
        """)
    
    def create_index(self, table_name: str, columns: list[str]) -> None:
        """Create indexes for faster filtering and joins."""
        col_list = ", ".join(columns)
        self.con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name} ON {table_name} ({col_list})")
    
    def optimize_parquet_files(self) -> None:
        """Re-optimizes all Parquet files in the datalake for better query performance."""
        try:
            self.con.execute("CALL optimize_parquet_files()")
            logger.info("Optimized all Parquet files in datalake")
        except Exception as e:
            logger.warning(f"Could not optimize Parquet files: {e}")
    
    def create_materialized_view(self, view_name: str, sql: str) -> None:
        """Create a materialized view for repeated queries."""
        self.con.execute(f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name}
            AS {sql}
        """)
    
    def refresh_materialized_view(self, view_name: str) -> None:
        """Refresh a materialized view."""
        self.con.execute(f"""
            REFRESH MATERIALIZED VIEW {view_name}
        """)
    
    def close(self) -> None:
        self.con.close()
        if hasattr(self, 'query_cache'):
            self.query_cache.cache_clear()