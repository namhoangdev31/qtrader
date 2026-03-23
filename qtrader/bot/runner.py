"""Main orchestrator for the autonomous trading bot."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import polars as pl

from qtrader.alpha.registry import AlphaEngine
from qtrader.core.bus import EventBus
from qtrader.core.event import EventType, FillEvent, OrderEvent, RiskEvent, SystemEvent
from qtrader.data.datalake import DataLake
from qtrader.execution.oms import UnifiedOMS
from qtrader.execution.safety import SafetyLayer
from qtrader.execution.sor import SmartOrderRouter
from qtrader.execution.brokers.binance import BinanceBrokerAdapter
from qtrader.execution.brokers.coinbase import CoinbaseBrokerAdapter
from qtrader.features.engine import FactorEngine
from qtrader.features.store import FeatureStore
from qtrader.ml.regime import RegimeDetector
from qtrader.portfolio.hrp import HRPOptimizer
from qtrader.portfolio.sizing import VolTargetSizer
from qtrader.risk.realtime import RealTimeRiskEngine
from qtrader.strategy.alpha_combiner import AlphaCombiner
from qtrader.analytics.performance import PerformanceAnalytics
from qtrader.analytics.telemetry import Telemetry
from qtrader.analytics.drift import DriftMonitor
from qtrader.pipeline.monitor import LiveMonitor
from bot.config import BotConfig
from bot.ev_optimizer import EVOptimizer
from bot.performance import PerformanceTracker
from bot.state import BotState, StateMachine
from bot.win_rate_optimizer import WinRateOptimizer

__all__ = ["TradingBot"]

_LOG = logging.getLogger("bot.runner")


def _load_baseline_metrics(path: str | None = None) -> object | None:
    """Load TearsheetMetrics from JSON if present (avoids backtest import in bot)."""
    from qtrader.backtest.tearsheet import TearsheetMetrics
    p = Path(path or "reports/latest_baseline.json").expanduser().absolute()
    if not p.exists():
        return None
    return TearsheetMetrics.from_json(p)


class TradingBot:
    """Autonomous trading bot lifecycle and concurrent loops.

    Lifecycle:
    1. __init__: load config, init components
    2. start(): INITIALIZING -> WARMING_UP -> TRADING
    3. _trading_loop(): runs 3 concurrent async loops (signal, risk, rebalance)
    4. emergency_shutdown(): cancel all orders, flatten, persist, exit
    """

    def __init__(self, config: BotConfig) -> None:
        """Wire up all components from config."""
        self.config = config
        self.bus = EventBus()
        self.oms = UnifiedOMS()
        self.safety = SafetyLayer()
        self.sor = SmartOrderRouter(self.oms)
        self.risk_engine = RealTimeRiskEngine()
        self.state = StateMachine()
        self.performance = PerformanceTracker(config.initial_capital)
        self.ev_optimizer = EVOptimizer()
        self.win_rate_opt = WinRateOptimizer()

        self.datalake = DataLake()
        self.feature_store = FeatureStore()
        self.feature_engine = FactorEngine(store=self.feature_store)
        self.alpha_engine = AlphaEngine(
            alpha_names=["momentum", "mean_reversion", "trend", "amihud", "vpin"],
            ic_window=30,
        )
        self.alpha_combiner = AlphaCombiner(method="ic_weighted")
        self.regime_detector = RegimeDetector(n_regimes=3, method="gmm")
        self.portfolio_optimizer = HRPOptimizer()
        self.vol_sizer = VolTargetSizer(target_vol=config.vol_target)

        self.execution_algo = None
        if config.execution_algo == "twap":
            from qtrader.execution.algos.twap import TWAPAlgo
            self.execution_algo = TWAPAlgo(duration_seconds=300, slice_count=5)

        self.backtest_baseline = _load_baseline_metrics()
        self.monitor = None
        if self.backtest_baseline is not None:

            self.monitor = LiveMonitor(
                tracker=self.performance,
                analytics=PerformanceAnalytics(),
                drift_monitor=DriftMonitor(),
                telemetry=Telemetry(),
                bus=self.bus,
                backtest_baseline=self.backtest_baseline,
            )

        if not self.config.feature_cols:
            self.config.feature_cols = self.feature_engine.get_all_feature_names()

        self._last_heartbeat: float = 0.0
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []
        self._primary_venue: str | None = None
        self._broker_symbol_map: dict[str, str] = {}

        self._init_execution_venues()

        self.bus.subscribe(EventType.FILL, self._on_fill)
        self.bus.subscribe(EventType.ORDER, self._on_order)
        self.bus.subscribe(EventType.RISK, self._on_risk_event)
        self.bus.subscribe(EventType.SYSTEM, self._on_system_event)

    async def _on_fill(self, event: FillEvent) -> None:
        """Handle fill: update OMS and performance."""
        await self.oms.on_fill(event)
        self.performance.record_fill(event, 0.0)
        _LOG.debug("Recorded fill %s %s @ %s", event.symbol, event.quantity, event.price)

    async def _on_risk_event(self, event: RiskEvent) -> None:
        """Handle risk breach: optionally transition to RISK_HALTED."""
        _LOG.warning("Risk event: %s %s", event.action, event.reason)

    async def _on_system_event(self, event: SystemEvent) -> None:
        """Handle system event (e.g. EMERGENCY_HALT from LiveMonitor)."""
        if event.action == "EMERGENCY_HALT":
            _LOG.critical("System EMERGENCY_HALT: %s", event.reason)
            await self.emergency_shutdown(event.reason)

    def _init_execution_venues(self) -> None:
        """Attach broker adapters based on configured venues (Coinbase default)."""
        venues = [v.strip().lower() for v in self.config.venues if str(v).strip()]
        for venue in venues:
            if venue == "coinbase":
                self.oms.add_venue("coinbase", CoinbaseBrokerAdapter())
            elif venue == "binance":
                self.oms.add_venue("binance", BinanceBrokerAdapter())
            else:
                _LOG.warning("Unsupported venue '%s' in config; skipping", venue)

        if not self.oms.adapters:
            raise ValueError(
                "No supported venues configured. Set venues to ['coinbase'] "
                "or ['binance'] in your bot YAML."
            )

        # Primary venue = first configured supported venue
        for venue in venues:
            if venue in self.oms.adapters:
                self._primary_venue = venue
                break
        if self._primary_venue is None:
            self._primary_venue = next(iter(self.oms.adapters.keys()))

    def _normalize_symbol_for_venue(self, symbol: str, venue: str) -> str:
        """Normalize symbol format for target venue."""
        if venue == "coinbase":
            return symbol.replace("/", "-").upper()
        if venue == "binance":
            return symbol.replace("/", "").replace("-", "").upper()
        return symbol

    def _adapt_order_for_venue(self, order: OrderEvent, venue: str) -> OrderEvent:
        """Return a venue-specific order (symbol formatting, etc.)."""
        normalized_symbol = self._normalize_symbol_for_venue(order.symbol, venue)
        if normalized_symbol == order.symbol:
            return order
        return OrderEvent(
            type=EventType.ORDER,
            symbol=normalized_symbol,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.price,
            side=order.side,
            order_id=order.order_id,
        )

    async def _pick_venue(self, order: OrderEvent) -> str:
        """Select venue for order routing."""
        if len(self.oms.adapters) == 1:
            return next(iter(self.oms.adapters.keys()))
        # Use SOR when multiple venues are configured.
        return await self.sor.get_best_venue(order.symbol, order.side)

    async def _on_order(self, event: OrderEvent) -> None:
        """Handle order: safety check -> route -> publish fills."""
        try:
            venue = await self._pick_venue(event)
            order = self._adapt_order_for_venue(event, venue)
            market_state = self.oms.get_market_state(venue, order.symbol)
            if not self.safety.check_order(order, market_state):
                await self.bus.publish(
                    RiskEvent(
                        reason="Safety check failed",
                        action="BLOCK",
                        metadata={"venue": venue, "symbol": order.symbol},
                    )
                )
                return
            broker_oid = await self.oms.route_order(venue, order)
            self._broker_symbol_map[broker_oid] = event.symbol
            fills = await self.oms.adapters[venue].get_fills(broker_oid)
            for fill in fills:
                symbol = self._broker_symbol_map.get(broker_oid, fill.symbol)
                if symbol != fill.symbol:
                    fill = FillEvent(
                        symbol=symbol,
                        quantity=fill.quantity,
                        price=fill.price,
                        commission=fill.commission,
                        side=fill.side,
                        order_id=fill.order_id,
                        fill_id=fill.fill_id,
                    )
                await self.bus.publish(fill)
        except Exception as e:
            _LOG.error("Order handling failed", exc_info=e)

    async def _fetch_latest_bars(self, symbol: str, n_bars: int = 500) -> pl.DataFrame:
        """Load last n_bars for symbol from datalake (run off-thread to avoid blocking)."""
        try:
            df = await asyncio.to_thread(
                self.datalake.load_data,
                symbol,
                "1d",
            )
            if df.is_empty():
                return df
            return df.tail(n_bars)
        except FileNotFoundError:
            return pl.DataFrame()

    async def _fetch_returns_matrix(self, lookback_days: int = 60) -> pl.DataFrame | None:
        """Fetch recent returns matrix for all config symbols for portfolio optimization."""
        try:
            raw = await asyncio.to_thread(
                self.datalake.load,
                self.config.symbols,
                "1d",
                last_n_days=lookback_days,
            )
            if raw.is_empty() or "close" not in raw.columns or "symbol" not in raw.columns:
                return None
            out: list[pl.DataFrame] = []
            for sym in self.config.symbols:
                sym_df = raw.filter(pl.col("symbol") == sym).sort("timestamp")
                if sym_df.height < 2:
                    continue
                ret = sym_df.select(pl.col("close").pct_change().alias(sym)).tail(lookback_days)
                out.append(ret)
            if not out:
                return None
            return pl.concat(out, how="horizontal")
        except Exception as e:
            _LOG.debug("Fetch returns matrix failed: %s", e)
            return None

    def _create_order(
        self,
        symbol: str,
        composite_signal: float,
        regime_id: int,
        price: float,
    ) -> OrderEvent | None:
        """Build OrderEvent from composite signal and current price."""
        if composite_signal == 0.0:
            return None
        side = "BUY" if composite_signal > 0 else "SELL"
        notional = self.config.initial_capital * 0.02
        qty = notional / price if price and price > 0 else 0.0
        if qty <= 0:
            return None
        return OrderEvent(
            type=EventType.ORDER,
            symbol=symbol,
            order_type="MARKET",
            quantity=qty,
            price=price,
            side=side,
            order_id=str(uuid.uuid4()),
        )

    async def _signal_loop(self) -> None:
        """Every signal_interval_s: fetch data, features, alpha, regime, gates, publish orders."""
        while self._running and self.state.can_trade():
            try:
                for symbol in self.config.symbols:
                    df = await self._fetch_latest_bars(symbol, n_bars=500)
                    if df.height < 50:
                        continue
                    features = self.feature_engine.compute_latest(df)
                    if features.is_empty():
                        continue
                    full = self.feature_engine.compute(df)
                    if full.is_empty():
                        continue
                    alpha_df = self.alpha_engine.compute_all(full)
                    if alpha_df.is_empty():
                        continue
                    signal = float(alpha_df["composite_alpha"][-1]) if "composite_alpha" in alpha_df.columns else 0.0
                    feature_cols = [c for c in self.config.feature_cols if c in alpha_df.columns]
                    if not feature_cols:
                        continue
                    try:
                        if not self.regime_detector._is_fitted:
                            self.regime_detector.fit(alpha_df, feature_cols)
                        regime_id, confidence = self.regime_detector.current_regime_confidence(alpha_df, feature_cols)
                        if self.regime_detector.is_transitioning(alpha_df, feature_cols):
                            continue
                    except Exception as e:
                        _LOG.debug("Regime check failed: %s", e)
                        regime_id, confidence = 0, 0.5
                    for name in self.alpha_engine.alpha_names:
                        if name in alpha_df.columns:
                            self.alpha_combiner.register_alpha(
                                name,
                                float(alpha_df[name][-1]),
                                self.alpha_engine._ic.get(name, 0.0),
                            )
                    composite = self.alpha_combiner.combine()
                    wr = self.performance.win_rate
                    wins = self.performance._fills_df.filter(pl.col("pnl") > 0)["pnl"]
                    losses = self.performance._fills_df.filter(pl.col("pnl") < 0)["pnl"]
                    avg_win = float(wins.mean()) if wins.len() else 1.0
                    avg_loss = abs(float(losses.mean())) if losses.len() else 1.0
                    if avg_win <= 0:
                        avg_win = 1.0
                    ev = self.ev_optimizer.compute_trade_ev(wr, float(avg_win), avg_loss, 10.0, self.config.initial_capital * 0.02)
                    ev_ok = self.ev_optimizer.should_enter(ev, 10.0 * self.config.initial_capital * 0.02 / 10_000.0)
                    wr_ok = self.win_rate_opt.signal_passes_filter(composite, confidence, 0.0, 0.0)
                    if ev_ok and wr_ok:
                        price = float(df["close"][-1]) if "close" in df.columns else 0.0
                        order = self._create_order(symbol, composite, regime_id, price)
                        if order is not None:
                            await self.bus.publish(order)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.error("Signal loop error", exc_info=e)
            self._last_heartbeat = time.time()
            await asyncio.sleep(float(self.config.signal_interval_s))

    async def _rebalance_loop(self) -> None:
        """Every rebalance_interval_s: get positions, optimizer weights, vol target, rebalance orders."""
        while self._running and self.state.can_trade():
            try:
                returns_df = await self._fetch_returns_matrix(lookback_days=60)
                if returns_df is None:
                    await asyncio.sleep(float(self.config.rebalance_interval_s))
                    continue
                symbols_present = [c for c in returns_df.columns if c in self.config.symbols]
                if not symbols_present:
                    await asyncio.sleep(float(self.config.rebalance_interval_s))
                    continue
                weights = self.portfolio_optimizer.optimize(returns_df)
                if not weights:
                    weights = {s: 1.0 / len(symbols_present) for s in symbols_present}
                positions_df = self.oms.position_manager.get_all_positions()
                current_prices: dict[str, float] = {}
                for sym in self.config.symbols:
                    pos = self.oms.position_manager.get_position(sym)
                    if pos and pos.qty != 0:
                        current_prices[sym] = pos.avg_cost
                equity = self.performance.initial_capital
                if self.performance._fills_df.height > 0:
                    equity = float(self.performance.equity_curve[-1])
                for symbol in symbols_present:
                    w = weights.get(symbol, 0.0)
                    if w <= 0:
                        continue
                    vol = float(returns_df[symbol].std()) if symbol in returns_df.columns else 0.01
                    target_val = self.vol_sizer.size(symbol, vol, equity)
                    price = current_prices.get(symbol, 100.0)
                    target_qty = target_val / price if price and price > 0 else 0.0
                    current_qty = 0.0
                    if not positions_df.is_empty() and "symbol" in positions_df.columns:
                        row = positions_df.filter(pl.col("symbol") == symbol)
                        if row.height > 0:
                            current_qty = float(row["qty"][0])
                    diff = target_qty - current_qty
                    if abs(diff) < 1e-6:
                        continue
                    side = "BUY" if diff > 0 else "SELL"
                    order = OrderEvent(
                        type=EventType.ORDER,
                        symbol=symbol,
                        order_type="MARKET",
                        quantity=abs(diff),
                        price=None,
                        side=side,
                        order_id=str(uuid.uuid4()),
                    )
                    await self.bus.publish(order)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.error("Rebalance loop error", exc_info=e)
            self._last_heartbeat = time.time()
            await asyncio.sleep(float(self.config.rebalance_interval_s))

    async def start(self) -> None:
        """Start the bot: transition to WARMING_UP then TRADING and run loops."""
        if self._running:
            return
        self._running = True
        self.state.transition(BotState.WARMING_UP, "start")
        await asyncio.sleep(0)
        self.state.transition(BotState.TRADING, "warmup complete")
        self._last_heartbeat = time.time()
        self._tasks = [
            asyncio.create_task(self.bus.start()),
            asyncio.create_task(self._signal_loop()),
            asyncio.create_task(self._risk_loop()),
            asyncio.create_task(self._rebalance_loop()),
        ]
        _LOG.info("TradingBot started; state=%s", self.state.state.value)

    async def _risk_loop(self) -> None:
        """Every risk_check_interval_s: check limits, halt if breach."""
        while self._running and self.state.can_trade():
            self._last_heartbeat = time.time()
            breaches = self.risk_engine.check_all_limits()
            if breaches:
                _LOG.warning("Risk breach: %s", [b.reason for b in breaches])
                try:
                    self.state.transition(BotState.RISK_HALTED, breaches[0].reason)
                except ValueError:
                    pass
            await asyncio.sleep(float(self.config.risk_check_interval_s))

    async def emergency_shutdown(self, reason: str) -> None:
        """Cancel all orders, flatten positions, persist state, exit."""
        _LOG.critical("Emergency shutdown: %s", reason)
        self._running = False
        try:
            self.state.transition(BotState.EMERGENCY, reason)
        except ValueError:
            pass
        await self.bus.shutdown()
        for t in self._tasks:
            t.cancel()
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except Exception:
            pass
        # Close broker sessions if supported
        for adapter in self.oms.adapters.values():
            close = getattr(adapter, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    pass
        _LOG.info("Emergency shutdown complete")

    @property
    def last_heartbeat(self) -> float:
        """Unix timestamp of last loop cycle (for /health endpoint)."""
        return self._last_heartbeat


def _run_bot(config_path: str) -> None:
    """Load config and run bot until SIGINT (for Makefile bot-start)."""
    cfg = BotConfig.from_yaml(config_path)
    bot = TradingBot(cfg)

    async def main() -> None:
        await bot.start()
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        asyncio.run(bot.emergency_shutdown("SIGINT"))


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "configs/bot_paper.yaml"
    _run_bot(path)


"""
# Pytest-style examples:
async def test_bot_start_transitions() -> None:
    cfg = BotConfig(symbols=["A"], venues=["coinbase"])
    bot = TradingBot(cfg)
    await bot.start()
    assert bot.state.can_trade()
    await bot.emergency_shutdown("test")
    assert not bot.state.can_trade()
"""
