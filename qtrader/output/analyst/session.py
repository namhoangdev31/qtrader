"""Extended AnalystSession – role-aware notebook workflow helpers for QTrader.

Roles
-----
RoleContext.ANALYST     – EDA, backtest reports, risk summaries, HTML export
RoleContext.RESEARCHER  – feature engineering, regime detection, ML experiments
RoleContext.TRADER      – live bot monitoring, execution audit, slippage analysis
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any

import numpy as np
import polars as pl

from qtrader.output.analytics.performance import PerformanceAnalytics
from qtrader.backtest.engine_vectorized import VectorizedEngine
from qtrader.input.data.datalake import DataLake
from qtrader.input.data.datalake_universal import UniversalDataLake
from qtrader.input.data.duckdb_client import DuckDBClient
from scripts.generate_data import generate_synthetic_data


class RoleContext(str, Enum):
    """Role context for AnalystSession.  Determines workflow guidance in notebooks."""
    ANALYST = "analyst"
    RESEARCHER = "researcher"
    TRADER = "trader"


class AnalystSession:
    """Full-featured analyst helpers for notebook workflows.

    Create a session and optionally specify the user's role::

        session = AnalystSession(role=RoleContext.ANALYST)

    All methods are useable regardless of role – the role is mainly used for
    ``info()`` guidance and future notebook auto-navigation.
    """

    def __init__(self, role: RoleContext | str = RoleContext.ANALYST) -> None:
        self._log = logging.getLogger("qtrader.output.analyst")
        self.role = RoleContext(role) if isinstance(role, str) else role
        self._log.info("AnalystSession initialised | role=%s", self.role.value)

    # ──────────────────────────────────────────────────────────────────
    # Data Loading
    # ──────────────────────────────────────────────────────────────────

    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        filter_sql: str | None = None,
        source: str = "duckdb",
    ) -> pl.DataFrame:
        """Load OHLCV from the datalake using DuckDB when available."""
        if source == "duckdb":
            try:
                return self._load_from_duckdb(symbol, timeframe, filter_sql)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                self._log.warning("DuckDB load failed (%s). Falling back to datalake.", exc)
                return self.load_from_datalake(symbol, timeframe)
        return self.load_from_datalake(symbol, timeframe)

    def load_from_datalake(self, symbol: str, timeframe: str) -> pl.DataFrame:
        """Load OHLCV from UniversalDataLake/DataLake fallback."""
        try:
            return self._load_from_universal(symbol, timeframe)
        except FileNotFoundError as exc:
            self._log.warning("UniversalDataLake missing (%s). Falling back to DataLake.", exc)
            try:
                return self._load_from_local_datalake(symbol, timeframe)
            except FileNotFoundError:
                self._log.warning("DataLake missing. Falling back to Live API.")
                return self.load_live_ohlcv(symbol, timeframe, days=7)

    def sample_ohlcv(self, symbol: str = "AAPL", days: int = 5) -> pl.DataFrame:
        """Generate synthetic OHLCV for quick analysis (no data source required)."""
        self._log.warning(f"⚠️ DATA_SOURCE: Generating SYNTHETIC data for {symbol}.")
        try:
            from scripts.generate_test_data import generate_synthetic_data
            return generate_synthetic_data(symbol=symbol, days=days)
        except ImportError:
            self._log.error("generate_synthetic_data function missing. Return empty df.")
            return pl.DataFrame()

    def load_live_ohlcv(self, symbol: str, timeframe: str, days: int = 7) -> pl.DataFrame:
        """Load real Coinbase REST API data and persist it to the DataLake."""
        from qtrader.input.data.market.coinbase_market import CoinbaseMarketDataClient
        from datetime import datetime, timedelta
        
        tf_map = {
            "1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE",
            "30m": "THIRTY_MINUTE", "1h": "ONE_HOUR", "2h": "TWO_HOUR", 
            "6h": "SIX_HOUR", "1d": "ONE_DAY"
        }
        granularity = tf_map.get(timeframe, "ONE_HOUR")
        
        client = CoinbaseMarketDataClient()
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days)
        df = client.get_candles(symbol, granularity, start=start_dt, end=end_dt)
        if not df.is_empty():
            self._log.info(f"Loaded {len(df)} live candles for {symbol} ({granularity})")
            
            # Persist to datalake
            try:
                from qtrader.input.data.datalake_universal import UniversalDataLake
                lake = UniversalDataLake()
                lake.save_data(df, symbol, timeframe)
            except Exception as e:
                self._log.warning(f"Failed to persist live data to DataLake: {e}")
                
        else:
            self._log.warning(f"No live data returned for {symbol}. Falling back to synthetic mock data.")
            df = self.sample_ohlcv(symbol, days)
        return df

    def get_live_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        """Fetch the live L2 orderbook from Coinbase."""
        from qtrader.input.data.market.coinbase_market import CoinbaseMarketDataClient
        client = CoinbaseMarketDataClient()
        return client.get_product_book(symbol, limit)

    def run_paper_simulation(self, symbol: str, strategy_fn: Any, timeframe: str = "1h", days: int = 7) -> Any:
        """Run a strategy logic function against live data to compute expected EV."""
        from qtrader.output.execution.paper_engine import PaperTradingEngine
        from qtrader.output.analytics.ev_calculator import EVCalculator
        
        df = self.load_live_ohlcv(symbol, timeframe, days)
        engine = PaperTradingEngine(starting_capital=10000.0)
        
        # applying strategy
        for row in df.iter_rows(named=True):
            market_state = {
                "bid": float(row["close"]) * 0.9999,
                "ask": float(row["close"]) * 1.0001,
                "top_depth": 5.0,
                "venue": "Coinbase_Sim"
            }
            order = strategy_fn(row)
            if order:
                engine.simulate_fill(order, market_state)
                
        calculator = EVCalculator(engine.closed_trades)
        return calculator.diagnose(symbol)

    def load_features(self, symbol: str, timeframe: str) -> pl.DataFrame:
        """Load pre-computed features from the FeatureStore.

        Returns an empty DataFrame if no features are stored yet.
        """
        from qtrader.input.features.store import FeatureStore

        store = FeatureStore()
        df = store.load_features(symbol=symbol, timeframe=timeframe)
        if df.is_empty():
            self._log.warning(
                "No features found for %s/%s – run feature engine first.", symbol, timeframe
            )
        return df

    # ──────────────────────────────────────────────────────────────────
    # Feature Engineering Helpers
    # ──────────────────────────────────────────────────────────────────

    def make_returns(self, df: pl.DataFrame, price_col: str = "close") -> pl.DataFrame:
        """Add *returns* column (pct_change of price_col) to DataFrame."""
        if price_col not in df.columns:
            raise ValueError(f"Missing price column: {price_col}")
        return df.with_columns(pl.col(price_col).pct_change().alias("returns"))

    def add_rolling_features(
        self,
        df: pl.DataFrame,
        windows: list[int] | None = None,
        price_col: str = "close",
    ) -> pl.DataFrame:
        """Add rolling mean, rolling std, and RSI-like momentum features.

        Parameters
        ----------
        df:
            DataFrame with at least *price_col*.
        windows:
            List of window sizes for rolling statistics. Default [5, 14, 21].
        """
        windows = windows or [5, 14, 21]
        cols = []
        for w in windows:
            cols.append(pl.col(price_col).rolling_mean(w).alias(f"sma_{w}"))
            cols.append(pl.col(price_col).rolling_std(w).alias(f"vol_{w}"))
        # Simple RSI (default 14)
        if "returns" not in df.columns:
            df = self.make_returns(df, price_col)
        w = 14
        cols.append(
            pl.col("returns")
            .clip(lower_bound=0)
            .rolling_mean(w)
            .alias("avg_gain")
        )
        cols.append(
            (-pl.col("returns").clip(upper_bound=0))
            .rolling_mean(w)
            .alias("avg_loss")
        )
        df = df.with_columns(cols)
        df = df.with_columns(
            (
                100
                - 100 / (1 + pl.col("avg_gain") / (pl.col("avg_loss") + 1e-10))
            ).alias("rsi_14")
        )
        return df

    # ──────────────────────────────────────────────────────────────────
    # EDA / Statistics
    # ──────────────────────────────────────────────────────────────────

    def describe(self, df: pl.DataFrame) -> dict[str, Any]:
        """Lightweight describe helper for notebooks."""
        return {
            "shape": df.shape,
            "columns": df.columns,
            "head": df.head(5),
        }

    def rich_describe(self, df: pl.DataFrame, numeric_only: bool = True) -> dict[str, Any]:
        """Extended descriptive statistics including skew, kurtosis, and outlier %.

        Returns a dict suitable for ``add_table`` in a ReportBuilder.
        """
        num_cols = [
            c for c in df.columns if df[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
        ] if numeric_only else df.columns

        stats: dict[str, Any] = {"shape": df.shape, "numeric_columns": num_cols, "columns": {}}
        for col in num_cols:
            s = df[col].drop_nulls()
            arr = s.to_numpy()
            q25, q75 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
            iqr = q75 - q25
            outlier_pct = float(((arr < q25 - 1.5 * iqr) | (arr > q75 + 1.5 * iqr)).mean() * 100)
            mean_ = float(arr.mean())
            std_ = float(arr.std())
            skew_ = float(((arr - mean_) ** 3).mean() / (std_ ** 3 + 1e-10))
            kurt_ = float(((arr - mean_) ** 4).mean() / (std_ ** 4 + 1e-10)) - 3.0
            stats["columns"][col] = {
                "count": len(arr),
                "mean": round(mean_, 6),
                "std": round(std_, 6),
                "min": round(float(arr.min()), 6),
                "q25": round(q25, 6),
                "median": round(float(np.median(arr)), 6),
                "q75": round(q75, 6),
                "max": round(float(arr.max()), 6),
                "skew": round(skew_, 4),
                "kurtosis": round(kurt_, 4),
                "null_pct": round(df[col].null_count() / len(df) * 100, 2),
                "outlier_pct (IQR)": round(outlier_pct, 2),
            }
        return stats

    def rich_describe_table(self, df: pl.DataFrame) -> pl.DataFrame:
        """Return rich_describe as a tidy Polars DataFrame for display in notebooks."""
        info = self.rich_describe(df)
        rows = []
        for col, metrics in info["columns"].items():
            row = {"column": col, **metrics}
            rows.append(row)
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    # ──────────────────────────────────────────────────────────────────
    # Backtest
    # ──────────────────────────────────────────────────────────────────

    def run_vector_backtest(
        self,
        df: pl.DataFrame,
        signal_col: str,
        price_col: str = "close",
        transaction_cost: float = 0.0001,
    ) -> pl.DataFrame:
        """Run vectorized backtest using VectorizedEngine."""
        engine = VectorizedEngine()
        return engine.backtest(
            df=df,
            signal_col=signal_col,
            price_col=price_col,
            transaction_cost=transaction_cost,
        )

    # ──────────────────────────────────────────────────────────────────
    # Performance Metrics
    # ──────────────────────────────────────────────────────────────────

    def performance_metrics(self, equity_curve: pl.Series | pl.DataFrame) -> dict[str, float]:
        """Compute core performance metrics (Sharpe, total return, max drawdown, vol)."""
        series = self._resolve_equity_series(equity_curve)
        return PerformanceAnalytics.calculate_metrics(series)  # type: ignore[arg-type]

    def compute_extended_metrics(
        self, equity_curve: pl.Series | pl.DataFrame, periods_per_year: int = 252
    ) -> dict[str, float]:
        """Extended performance metrics: Sortino, Calmar, Win Rate, Profit Factor.

        Parameters
        ----------
        equity_curve:
            Equity curve as a Polars Series or single-column DataFrame.
        periods_per_year:
            Annualisation factor (252 for daily, 365 for crypto daily, 8760 hourly).
        """
        series = self._resolve_equity_series(equity_curve)
        base = PerformanceAnalytics.calculate_metrics(series)  # type: ignore[arg-type]

        returns = series.pct_change().drop_nulls().to_numpy()
        ann = float(periods_per_year)

        # Sortino
        downside = returns[returns < 0]
        downside_vol = float(np.std(downside) * np.sqrt(ann)) if len(downside) > 0 else 1e-10
        ann_ret = float(returns.mean() * ann)
        sortino = ann_ret / downside_vol if downside_vol > 0 else 0.0

        # Calmar
        max_dd = abs(base["max_drawdown"])
        calmar = ann_ret / max_dd if max_dd > 0 else 0.0

        # Win Rate
        win_rate = float((returns > 0).mean())

        # Profit Factor = sum(gains) / abs(sum(losses))
        gains = returns[returns > 0].sum()
        losses = abs(returns[returns < 0].sum())
        profit_factor = gains / losses if losses > 0 else float("inf")

        # Omega Ratio (threshold = 0)
        omega = gains / losses if losses > 0 else float("inf")

        return {
            **base,
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "omega_ratio": round(omega, 4),
            "periods_per_year": periods_per_year,
        }

    # ──────────────────────────────────────────────────────────────────
    # Alpha Scoring (Researcher)
    # ──────────────────────────────────────────────────────────────────

    def run_alpha_score(
        self,
        df: pl.DataFrame,
        forward_periods: list[int] | None = None,
    ) -> pl.DataFrame:
        """Compute forward-return alpha scores for each row in *df*.

        Returns a new DataFrame with additional ``fwd_ret_{n}`` columns (forward
        returns over *n* periods) plus a composite ``alpha_score``.

        This is a standalone scoring helper – it does NOT require a fitted model.
        Use the Researcher notebooks to train and register actual alpha models via MLflow.
        """
        forward_periods = forward_periods or [1, 5, 10]
        if "returns" not in df.columns:
            df = self.make_returns(df)
        cols = []
        for n in forward_periods:
            cols.append(pl.col("returns").shift(-n).alias(f"fwd_ret_{n}"))
        df = df.with_columns(cols)
        # Simple composite: equal-weighted average of available forward returns
        fwd_cols = [f"fwd_ret_{n}" for n in forward_periods]
        df = df.with_columns(
            pl.concat_list([pl.col(c) for c in fwd_cols])
            .list.mean()
            .alias("alpha_score")
        )
        return df

    # ──────────────────────────────────────────────────────────────────
    # Live API (Trader)
    # ──────────────────────────────────────────────────────────────────

    def connect_live_api(
        self,
        host: str = "localhost",
        port: int = 8000,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Fetch live bot status from the QTrader FastAPI ``/status`` endpoint.

        Parameters
        ----------
        host:
            Host where the FastAPI app is running (default ``localhost``).
        port:
            Port (default ``8000``).
        timeout:
            HTTP timeout in seconds.

        Returns
        -------
        dict
            JSON payload from ``/status``.  Keys: ``uptime_seconds``,
            ``regime``, ``active_model``, ``engine_status``, ``iteration``, etc.

        Raises
        ------
        RuntimeError
            If the API is unreachable.
        """
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for connect_live_api. Install with: pip install httpx"
            ) from exc

        url = f"http://{host}:{port}/status"
        try:
            resp = httpx.get(url, timeout=timeout)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            self._log.info("Live API connected – status: %s", data.get("engine_status"))
            return data
        except Exception as exc:
            raise RuntimeError(
                f"Could not reach QTrader API at {url}: {exc}\n"
                "Make sure the bot is running and the API is started (see docs/analyst.md)."
            ) from exc

    def ping_live_api(self, host: str = "localhost", port: int = 8000) -> bool:
        """Return True if the FastAPI health endpoint is reachable."""
        try:
            import httpx

            r = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────
    # Report Export
    # ──────────────────────────────────────────────────────────────────

    def export_report(
        self,
        title: str,
        sections: dict[str, Any],
        path: str = "analyst_report.html",
    ) -> str:
        """Build and save an HTML report from a dict of sections.

        Parameters
        ----------
        title:
            Report heading.
        sections:
            Ordered dict mapping section heading → content.
            Content can be:
            * ``str`` – rendered as text paragraph
            * ``pl.DataFrame`` – rendered as HTML table
            * ``dict`` – flat metric dict (key → numeric value), rendered as 2-col table
            * matplotlib ``Figure`` – embedded as base64 PNG

        Returns
        -------
        str
            Absolute path to the saved HTML file.

        Example
        -------
        ::

            path = session.export_report(
                title="BTC-USD Backtest",
                sections={
                    "Overview": "Strategy: momentum 1h.",
                    "Metrics": metrics_dict,
                    "Equity Curve": equity_figure,
                },
                path="reports/btc_backtest.html",
            )
        """
        from qtrader.output.analyst.report import ReportBuilder

        rb = ReportBuilder(title)
        for heading, content in sections.items():
            if isinstance(content, str):
                rb.add_text(heading, content)
            elif isinstance(content, pl.DataFrame):
                rb.add_table(heading, content)
            elif isinstance(content, dict):
                rb.add_table(heading, content)
            elif isinstance(content, pl.Series):
                rb.add_polars_plot(heading, content)
            else:
                # Assume matplotlib Figure
                try:
                    rb.add_figure(heading, content)
                except Exception as exc:
                    self._log.warning("Skipping section %r: %s", heading, exc)
        saved = rb.save(path)
        return str(saved)

    # ──────────────────────────────────────────────────────────────────
    # Utility / Guidance
    # ──────────────────────────────────────────────────────────────────

    def info(self) -> None:
        """Print role-specific workflow guidance to stdout."""
        guides = {
            RoleContext.ANALYST: (
                "📊 Quant Analyst Workflow\n"
                "  1. load_ohlcv / sample_ohlcv → load market data\n"
                "  2. make_returns + add_rolling_features → prepare features\n"
                "  3. run_vector_backtest → backtest a signal\n"
                "  4. compute_extended_metrics → Sharpe, Sortino, Calmar, Win Rate\n"
                "  5. export_report → save interactive HTML report\n"
                "\n  📓 Notebooks: notebooks/analyst/01_EDA_Report.ipynb, ...\n"
            ),
            RoleContext.RESEARCHER: (
                "🔬 Quant Researcher Workflow\n"
                "  1. load_ohlcv → raw OHLCV\n"
                "  2. add_rolling_features → compute & store features via FeatureStore\n"
                "  3. run_alpha_score → forward-return scoring\n"
                "  4. Use MLflow for experiment tracking (see notebooks/researcher/)\n"
                "  5. load_features → pull pre-computed features\n"
                "\n  📓 Notebooks: notebooks/researcher/01_Feature_Lab.ipynb, ...\n"
            ),
            RoleContext.TRADER: (
                "⚡ Quant Trader Workflow\n"
                "  1. ping_live_api → check if bot is running\n"
                "  2. connect_live_api → fetch live status (P&L, regime, active model)\n"
                "  3. load_ohlcv + fills → execution audit\n"
                "  4. compute_extended_metrics on live equity curve\n"
                "\n  📓 Notebooks: notebooks/trader/01_Live_Monitor.ipynb, ...\n"
            ),
        }
        print(guides.get(self.role, "QTrader AnalystSession ready."))

    def __repr__(self) -> str:
        return f"AnalystSession(role={self.role.value!r})"

    # ──────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────

    def _resolve_equity_series(self, equity_curve: pl.Series | pl.DataFrame) -> pl.Series:
        if isinstance(equity_curve, pl.DataFrame):
            if "equity_curve" not in equity_curve.columns:
                raise ValueError("DataFrame must contain an 'equity_curve' column")
            return equity_curve["equity_curve"]
        return equity_curve

    def _load_from_duckdb(
        self, symbol: str, timeframe: str, filter_sql: str | None
    ) -> pl.DataFrame:
        client = DuckDBClient()
        try:
            return client.query_datalake(symbol=symbol, timeframe=timeframe, filter_sql=filter_sql)
        finally:
            client.close()

    def _load_from_universal(self, symbol: str, timeframe: str) -> pl.DataFrame:
        lake = UniversalDataLake()
        return lake.load_data(symbol=symbol, timeframe=timeframe)

    def _load_from_local_datalake(self, symbol: str, timeframe: str) -> pl.DataFrame:
        lake = DataLake()
        return lake.load_data(symbol=symbol, timeframe=timeframe)
