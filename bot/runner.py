"""TradingBot runner: signal and rebalance loops for live trading.

This module implements the TradingBot class with the signal generation and
portfolio rebalancing loops as specified in the pipeline architecture.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import polars as pl

from qtrader.core.config import BotConfig
from qtrader.core.event_bus import EventBus, EventType, OrderEvent, FillEvent
from qtrader.core.state import StateMachine
from qtrader.datalake import DataLake
from qtrader.features.engine import FactorEngine
from qtrader.feature_store import FeatureStore
from qtrader.alpha.engine import AlphaEngine
from qtrader.alpha.combiner import AlphaCombiner
from qtrader.ml.regime_detector import RegimeDetector
from qtrader.risk.real_time_risk_engine import RealTimeRiskEngine
from qtrader.execution.execution_engine import UnifiedOMS, TWAPAlgo
from qtrader.portfolio.allocator import HRPOptimizer, CVaROptimizer
from qtrader.portfolio.vol_sizer import VolTargetSizer
from qtrader.bot.performance import PerformanceTracker
from qtrader.bot.optimizers import EVOptimizer, WinRateOptimizer

logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot that runs signal and rebalance loops.

    The bot orchestrates live trading by:
    - Fetching latest market data
    - Computing features and alpha signals
    - Applying regime and EV/win-rate filters
    - Generating and executing orders
    - Periodically rebalancing the portfolio
    """

    def __init__(self, config: BotConfig) -> None:
        """Initialize the TradingBot with all required components.

        Args:
            config: BotConfig instance containing strategy parameters.
        """
        # --- EXISTING (keep) ---
        self.bus = EventBus()
        self.oms = UnifiedOMS()
        self.risk_engine = RealTimeRiskEngine()
        self.state = StateMachine()
        self.performance = PerformanceTracker(config.initial_capital)
        self.ev_optimizer = EVOptimizer()
        self.win_rate_opt = WinRateOptimizer()

        # --- NEW — add all these: ---
        self.datalake = DataLake()
        self.feature_engine = FactorEngine(store=FeatureStore())
        self.alpha_engine = AlphaEngine(
            alpha_names=["momentum", "mean_reversion", "trend", "amihud", "vpin"],
            ic_window=30,
        )
        self.alpha_combiner = AlphaCombiner(method="ic_weighted")
        self.regime_detector = RegimeDetector(n_regimes=3, method="gmm")
        self.portfolio_optimizer = HRPOptimizer()  # or CVaROptimizer
        self.vol_sizer = VolTargetSizer(target_vol=config.vol_target)
        self.execution_algo = (
            TWAPAlgo(duration_seconds=300, slice_count=5)
            if config.execution_algo == "twap"
            else None
        )

        # Load backtest baseline for LiveMonitor (if exists)
        baseline_path = "reports/latest_baseline.json"
        self.backtest_baseline = (
            TearsheetMetrics.from_json(baseline_path)
            if Path(baseline_path).exists()
            else None
        )

        if self.backtest_baseline:
            self.monitor = LiveMonitor(
                tracker=self.performance,
                analytics=PerformanceAnalytics(),
                drift_monitor=DriftMonitor(),
                telemetry=Telemetry(),
                bus=self.bus,
                backtest_baseline=self.backtest_baseline,
            )

        self.config = config
        self.config.feature_cols = self.feature_engine.get_all_feature_names()

        # Subscribe all handlers
        self.bus.subscribe(EventType.FILL, self._on_fill)
        self.bus.subscribe(EventType.RISK, self._on_risk_event)
        self.bus.subscribe(EventType.SYSTEM, self._on_system_event)
        self.bus.subscribe(EventType.REGIME_CHANGE, self._on_regime_change)

        self._running = False

    async def _signal_loop(self) -> None:
        """Generate trading signals based on latest market data.

        Every signal_interval_s seconds:
        1. Fetch latest OHLCV bars from DataLake (last N bars per symbol)
        2. Compute features: feature_engine.compute_latest(df_per_symbol)
        3. Compute alpha signals: alpha_engine.compute_all(features_df)
        4. Detect regime: regime_detector.current_regime_confidence(features_df, feature_cols)
        5. Combine signals: alpha_combiner.combine() → composite_signal
        6. EV gate: ev_optimizer.should_enter(signal, win_rate, avg_win, avg_loss, costs)
        7. Win rate gate: win_rate_opt.filter(signal, regime_confidence)
        8. If passed both gates: publish OrderEvent via EventBus
        9. Update PerformanceTracker with current equity from OMS.get_pnl()
        """
        while self._running and self.state.can_trade():
            try:
                for symbol in self.config.symbols:
                    df = await self._fetch_latest_bars(symbol, n_bars=500)
                    if df.height < 50:
                        continue

                    # Feature computation
                    features = self.feature_engine.compute_latest(df)

                    # Alpha signal
                    alpha_df = self.alpha_engine.compute_all(df)
                    signal = float(alpha_df["composite_alpha"][-1])

                    # Regime gate
                    regime_id, confidence = self.regime_detector.current_regime_confidence(
                        alpha_df, self.config.feature_cols
                    )
                    if self.regime_detector.is_transitioning(
                        alpha_df, self.config.feature_cols
                    ):
                        continue  # Skip during regime transitions (higher uncertainty)

                    # IC-weighted combination
                    composite = self.alpha_combiner.combine()

                    # EV + Win Rate filter
                    ev_ok = self.ev_optimizer.should_enter(
                        composite, regime_confidence=confidence
                    )
                    wr_ok = self.win_rate_opt.filter(composite, confidence)

                    if ev_ok and wr_ok:
                        order = self._create_order(symbol, composite, regime_id)
                        if order:
                            await self.bus.publish(order)
            except asyncio.CancelledError:
                raise  # Propagate cancellation
            except Exception as e:
                logger.error("Signal loop error", exc_info=e)

            await asyncio.sleep(float(self.config.signal_interval_s))

    async def _rebalance_loop(self) -> None:
        """Periodically rebalance the portfolio to target weights.

        Every rebalance_interval_s seconds:
        1. Get current positions from OMS.position_manager
        2. Get latest features for all symbols in universe
        3. Run portfolio optimizer (HRP or CVaR) on recent returns
        4. Compute target weights
        5. Apply VolTargetSizer: scale weights to hit vol_target
        6. Compute rebalance orders (current_weight → target_weight diff)
        7. Apply execution algo: TWAP/VWAP/market based on config
        8. Publish rebalance orders to EventBus
        """
        while self._running and self.state.can_trade():
            try:
                returns_df = await self._fetch_returns_matrix(lookback_days=60)
                if returns_df is None:
                    await asyncio.sleep(float(self.config.rebalance_interval_s))
                    continue

                # Portfolio optimization
                if self.config.strategy == "hrp":
                    weights = self.portfolio_optimizer.optimize(returns_df)
                else:
                    weights = {
                        s: 1.0 / len(self.config.symbols)
                        for s in self.config.symbols
                    }

                # Vol targeting
                current_positions = self.oms.position_manager.get_all_positions()
                rebalance_orders = self._compute_rebalance_orders(
                    weights, current_positions
                )

                for order in rebalance_orders:
                    await self.bus.publish(order)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Rebalance loop error", exc_info=e)

            await asyncio.sleep(float(self.config.rebalance_interval_s))

    # -----------------------------------------------------------------------
    # Helper methods (to be implemented or adapted from existing codebase)
    # -----------------------------------------------------------------------

    async def _fetch_latest_bars(
        self, symbol: str, n_bars: int = 500
    ) -> pl.DataFrame:
        """Fetch the latest OHLCV bars for a symbol from the datalake.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT").
            n_bars: Number of bars to fetch.

        Returns:
            Polars DataFrame with OHLCV data.
        """
        # Placeholder implementation - replace with actual datalake call
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        # We need to calculate start_date based on n_bars and timeframe.
        # For simplicity, we assume the datalake can return the last n_bars.
        # This method should be adapted to the actual DataLake interface.
        df = await self.datalake.load(
            symbols=[symbol],
            timeframe=self.config.timeframe,  # Assuming config has timeframe
            start_date="",  # Will be interpreted as last_n_bars
            end_date=end_date,
            last_n_days=None,  # We'll use n_bars instead of days
        )
        # If the datalake returns more than n_bars, we slice
        if df.height > n_bars:
            df = df.tail(n_bars)
        return df

    def _create_order(
        self, symbol: str, signal: float, regime_id: int
    ) -> OrderEvent | None:
        """Create an order event based on the signal and regime.

        Args:
            symbol: Trading symbol.
            signal: Composite signal value.
            regime_id: Current regime identifier.

        Returns:
            OrderEvent if an order should be placed, None otherwise.
        """
        # Placeholder: implement actual order creation logic
        # This should consider signal strength, regime, position limits, etc.
        if abs(signal) < 0.1:  # Example threshold
            return None

        # Determine order side and size based on signal
        side = "buy" if signal > 0 else "sell"
        # Example: fixed size for now, should be dynamic based on signal and volatility
        qty = 0.001  # Example quantity

        # Create OrderEvent (assuming the constructor matches)
        order = OrderEvent(
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=qty,
            price=0.0,  # Market order, price ignored
            timestamp=datetime.utcnow(),
        )
        return order

    async def _fetch_returns_matrix(self, lookback_days: int = 60) -> pl.DataFrame | None:
        """Fetch historical returns for all symbols in the universe.

        Args:
            lookback_days: Number of days of returns to fetch.

        Returns:
            Polars DataFrame with returns (columns: symbols, rows: timestamps),
            or None if insufficient data.
        """
        # Placeholder: fetch OHLCV data for all symbols and compute returns
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (
            datetime.utcnow() - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")

        try:
            # Load data for all symbols
            df = await self.datalake.load(
                symbols=self.config.symbols,
                timeframe="1d",  # Assuming daily returns for rebalancing
                start_date=start_date,
                end_date=end_date,
            )
            if df.is_empty():
                return None

            # Pivot to have symbols as columns and timestamp as index
            # We'll assume df has: timestamp, symbol, close
            # We want to compute returns per symbol
            # This is a simplified example; actual implementation may vary
            returns = (
                df.sort("timestamp")
                .group_by("symbol")
                .agg(
                    [
                        pl.col("close")
                        .pct_change()
                        .fill_null(0.0)
                        .alias("returns")
                    ]
                )
                .pivot(
                    index="timestamp",
                    columns="symbol",
                    values="returns",
                    aggregate_function=None,
                )
                .fill_null(0.0)
            )
            return returns
        except Exception as e:
            logger.error("Failed to fetch returns matrix: %s", e)
            return None

    def _compute_rebalance_orders(
        self, target_weights: dict[str, float], current_positions: dict[str, Any]
    ) -> list[OrderEvent]:
        """Compute rebalance orders to move from current to target weights.

        Args:
            target_weights: Dict mapping symbol to target weight (float).
            current_positions: Dict from OMS.PositionManager with current positions.

        Returns:
            List of OrderEvent objects to execute the rebalancing.
        """
        # Placeholder: implement actual rebalancing logic
        orders = []
        # We need to get current prices to compute the value of current positions
        # and then compute the target quantity for each symbol.
        # This is a simplified example.

        # Get current prices (placeholder)
        current_prices = {}
        for symbol in self.config.symbols:
            # In a real system, we would get the latest price from the market data
            current_prices[symbol] = 100.0  # Example price

        # Compute current portfolio value
        total_value = 0.0
        for symbol, pos in current_positions.items():
            qty = pos.get("quantity", 0.0)
            price = current_prices.get(symbol, 0.0)
            total_value += abs(qty * price)

        # For each symbol, compute target quantity and current quantity
        for symbol in self.config.symbols:
            target_weight = target_weights.get(symbol, 0.0)
            target_value = total_value * target_weight
            target_qty = target_value / current_prices.get(symbol, 1.0)

            current_qty = current_positions.get(symbol, {}).get("quantity", 0.0)
            qty_diff = target_qty - current_qty

            if abs(qty_diff) < 1e-6:  # Essentially zero
                continue

            side = "buy" if qty_diff > 0 else "sell"
            order = OrderEvent(
                symbol=symbol,
                side=side,
                order_type="market",
                quantity=abs(qty_diff),
                price=0.0,
                timestamp=datetime.utcnow(),
            )
            orders.append(order)

        return orders

    # -----------------------------------------------------------------------
    # Event handlers (required by the event bus subscriptions)
    # -----------------------------------------------------------------------

    async def _on_fill(self, event: FillEvent) -> None:
        """Handle FillEvent from the execution engine.

        Args:
            event: FillEvent instance.
        """
        logger.info("Fill received: %s", event)
        # Update performance tracker with fill
        self.performance.update_fill(event)

    async def _on_risk_event(self, event: Any) -> None:
        """Handle risk events from the risk engine.

        Args:
            event: Risk event (type depends on the risk engine).
        """
        logger.warning("Risk event: %s", event)
        # Example: halt trading if risk limits are breached
        if getattr(event, "breach", False):
            self.state.halt()

    async def _on_system_event(self, event: Any) -> None:
        """Handle system events (e.g., from LiveMonitor).

        Args:
            event: SystemEvent instance.
        """
        logger.info("System event: %s", event)
        if getattr(event, "action", None) == "EMERGENCY_HALT":
            self.state.halt()

    async def _on_regime_change(self, event: Any) -> None:
        """Handle regime change events.

        Args:
            event: Regime change event.
        """
        logger.info("Regime change: %s", event)
        # Could adjust strategy parameters based on regime

    # -----------------------------------------------------------------------
    # Start/stop methods
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Start the trading bot's signal and rebalance loops."""
        logger.info("Starting TradingBot")
        self._running = True
        # Start the loops as concurrent tasks
        signal_task = asyncio.create_task(self._signal_loop())
        rebalance_task = asyncio.create_task(self._rebalance_loop())
        await asyncio.gather(signal_task, rebalance_task)

    async def stop(self) -> None:
        """Stop the trading bot."""
        logger.info("Stopping TradingBot")
        self._running = False
        # The loops will exit when _running is False


# ---------------------------------------------------------------------------
# Inline unit-test examples (doctest style)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import doctest

    doctest.testmod()

    # Example usage (not executed unless run directly)
    # async def main():
    #     config = BotConfig(...)  # Fill in required fields
    #     bot = TradingBot(config)
    #     await bot.start()
    #
    # asyncio.run(main())