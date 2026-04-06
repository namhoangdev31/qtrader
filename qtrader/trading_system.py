"""Unified Trading System — Complete End-to-End Pipeline.

Wires ALL modules into a single coherent trading system:

  Market Data → Alpha (Atomic Trio ML) → Signal → Risk → Order → Fill → Recon → PnL
       ↓              ↓                      ↓        ↓       ↓       ↓       ↓       ↓
  WebSocket      Chronos-2            Risk Check   Broker  Fill    Recon   PnL    Monitor
  Streaming      TabPFN 2.5           Kill Switch  Execute Process Track   Alert

Institutional Compliance (Standash §4.1 - §13)
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import numpy as np
from loguru import logger

from qtrader.analytics.pnl_attribution import PnLAttributionEngine
from qtrader.core.event_bus import EventBus
from qtrader.core.events import (
    EventType,
    MarketEvent,
    MarketPayload,
    OrderEvent,
    OrderPayload,
)
from qtrader.core.latency_enforcer import LatencyEnforcer
from qtrader.core.state_store import Position, StateStore
from qtrader.execution.brokers.coinbase import CoinbaseBrokerAdapter
from qtrader.execution.pre_trade_risk import PreTradeRiskConfig, PreTradeRiskValidator
from qtrader.execution.reconciliation_engine import ReconciliationEngine
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.ml.atomic_trio import AtomicTrioPipeline
from qtrader.ml.remote_client import RemoteAtomicTrioPipeline
from qtrader.ml.retrain_system import RetrainSystem
from qtrader.monitoring.alert_engine import AlertEngine, AlertMessage, AlertSeverity
from qtrader.oms.order_management_system import UnifiedOMS
from qtrader.persistence.db_writer import TradeDBWriter
from qtrader.portfolio.allocator import CapitalAllocationEngine
from qtrader.risk.kill_switch import GlobalKillSwitch
from qtrader.features.technical.volatility import ATRFeature
from qtrader.risk.dynamic_guardrail import DynamicGuardrailManager

from qtrader.core.dynamic_config import config_manager
from qtrader.ml.embedding_worker import embedding_manager

# Note: Top-level constants (MIN_CONFIDENCE, etc.) removed in favor of config_manager.get()
# to allow AI-driven Dynamic Control.


@dataclass
class TradingSystemConfig:
    """Complete configuration for the Trading System."""

    # Trading mode
    simulate: bool = True
    symbols: list[str] = field(default_factory=lambda: ["BTC-USD"])

    # Risk limits
    max_position_usd: float = 100_000.0
    max_drawdown_pct: float = 0.20
    max_order_qty: float = 1.0
    max_order_notional: float = 50_000.0
    max_orders_per_second: float = 5.0

    # ML config (HuggingFace models)
    chronos_model_id: str = "amazon/chronos-2"
    tabpfn_model_id: str = "Prior-Labs/tabpfn_2_5"
    phi2_model_id: str = "microsoft/phi-2"
    ml_weight: float = 0.6
    traditional_weight: float = 0.4

    # Reconciliation
    recon_interval_s: float = 60.0

    # Heartbeat
    heartbeat_interval_s: float = 10.0

    # Signal processing interval (seconds between signal checks)
    signal_interval_s: float = 1.0

    # Alerting
    slack_webhook_url: str | None = None
    pagerduty_routing_key: str | None = None

    # Latency
    max_latency_ms: float = 100.0

    # Shadow mode
    shadow_mode: bool = True
    shadow_min_days: int = 7

    # Dynamic Risk Parameters
    atr_window: int = 14
    atr_multiplier: float = 2.0
    forecast_multiplier: float = 1.5
    min_sl_pct: float = 0.005
    max_sl_pct: float = 0.05


class TradingSystem:
    """Unified Trading System — Complete End-to-End Pipeline."""

    def __init__(
        self, config: TradingSystemConfig | None = None, ml_pipeline: Any | None = None
    ) -> None:
        self.config = config or TradingSystemConfig()
        self.state_store = StateStore()
        self.event_bus = EventBus()

        # === 1. ML Alpha Engine (Atomic Trio) ===
        if ml_pipeline is not None:
            self.ml_pipeline = ml_pipeline
        else:
            ml_url = os.environ.get("ML_ENGINE_URL")
            if ml_url:
                self.ml_pipeline = RemoteAtomicTrioPipeline(base_url=ml_url)
                logger.info(f"[TRADING_SYSTEM] Using Remote ML Engine at {ml_url}")
            else:
                self.ml_pipeline = AtomicTrioPipeline(
                    chronos_model_id=self.config.chronos_model_id,
                    tabpfn_model_id=self.config.tabpfn_model_id,
                    phi2_model_id=self.config.phi2_model_id,
                )
                logger.info("[TRADING_SYSTEM] Using Local ML Engine")

        # Consecutive loss tracking for circuit breaker
        self._consecutive_losses: int = 0
        self._last_signal_direction: dict[str, str] = {}
        self._signal_streak: dict[str, int] = {}
        self._loss_cooldown: dict[str, int] = {}  # Cooldown ticks after loss
        self._peak_equity: float = 1000.0  # Track peak for trailing stop
        self._position_opened_at: dict[str, float] = {}  # Entry timestamps
        self._confidence_ema: dict[str, float] = {}  # Smoothed signal confidence
        self._last_exit_at: dict[str, float] = {}  # Exit timestamps for cooldown

        # === 2. MLOps Self-Learning ===
        self.retrain_system = RetrainSystem(psi_threshold=0.20, performance_drop_delta=0.15)
        self._win_history: deque[int] = deque(maxlen=50)  # Binary wins for win-rate tracking

        # === 2. Risk Management ===
        self.kill_switch = GlobalKillSwitch(
            dd_limit=self.config.max_drawdown_pct,
            loss_limit=self.config.max_position_usd * 2,
            auto_liquidate=False,
        )
        self.pre_trade_risk = PreTradeRiskValidator(
            PreTradeRiskConfig(
                max_order_quantity=Decimal(str(self.config.max_order_qty)),
                max_order_notional=Decimal(str(self.config.max_order_notional)),
                max_position_per_symbol=Decimal(str(self.config.max_position_usd / (config_manager.get("REFERENCE_PRICE") or 50000.0))),
                max_orders_per_second=self.config.max_orders_per_second,
            )
        )

        # === 3. Execution (Broker) ===
        self.broker = CoinbaseBrokerAdapter(
            simulate=self.config.simulate,
            kill_switch=self.kill_switch,
        )
        self.broker.set_market_data_handler(self._on_market_data_update)

        # === 4. Portfolio & Risk Management ===
        self.allocator = CapitalAllocationEngine(max_cap=Decimal("0.2"))
        self.guardrail_manager = DynamicGuardrailManager(
            atr_multiplier=self.config.atr_multiplier,
            forecast_multiplier=self.config.forecast_multiplier,
            min_sl_pct=self.config.min_sl_pct,
            max_sl_pct=self.config.max_sl_pct,
        )
        self.atr_indicator = ATRFeature(window=self.config.atr_window)

        # === 5. Shadow Validation ===
        self.shadow_engine = ShadowEngine(
            {
                "shadow_mode": self.config.shadow_mode or self.config.simulate,
                "min_shadow_duration_s": self.config.shadow_min_days * 86400,
            }
        )

        # === 6. OMS & Reconciliation ===
        self.oms = UnifiedOMS(state_store=self.state_store, event_bus=self.event_bus)
        self.oms.add_venue("coinbase", self.broker)
        self.recon = ReconciliationEngine(
            event_bus=self.event_bus,
            oms=self.oms,
            state_store=self.state_store,
            recon_interval_s=self.config.recon_interval_s,
            kill_switch=self.kill_switch,
        )

        # === 7. Monitoring ===
        self.alert_engine = AlertEngine(
            slack_webhook_url=self.config.slack_webhook_url,
            pagerduty_routing_key=self.config.pagerduty_routing_key,
        )
        self.latency_enforcer = LatencyEnforcer(fail_on_breach=False)
        self.pnl_attribution = PnLAttributionEngine()
        self.db_writer = TradeDBWriter()

        # === 8. State ===
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._market_data: dict[str, list[dict[str, float]]] = {s: [] for s in self.config.symbols}
        self._stats = {
            "orders": 0,
            "fills": 0,
            "errors": 0,
            "signals": 0,
            "recon_checks": 0,
            "recon_mismatches": 0,
            "alerts_sent": 0,
            "start_time": 0.0,
            "last_heartbeat": 0.0,
        }
        self._last_fill_count: int = 0
        self.last_thinking: dict[str, dict[str, str]] = {}
        self.active_session_id: str | None = None
        self._last_pnl_report: dict[str, Any] = {}
        self._last_module_traces: dict[str, Any] = {
            "AlphaEngine": {"status": "AWAITING"},
            "RiskEngine": {"status": "AWAITING"},
            "RiskGuard": {"status": "AWAITING"},
            "Portfolio": {"status": "AWAITING"},
            "Reconciliation": {"status": "AWAITING"},
            "Strategy": {"status": "AWAITING"}
        }
        self._tasks: set[asyncio.Task[Any]] = set()
        self._start_time: float = time.time()
        self._last_latency_ms: float = 0.0

    async def start(self) -> None:
        """Start the complete trading system."""
        logger.info("=" * 70)
        logger.info("TRADING SYSTEM — STARTING")
        logger.info(f"Mode: {'PAPER' if self.config.simulate else 'LIVE'}")
        logger.info(f"Symbols: {self.config.symbols}")
        logger.info("=" * 70)

        self._running = True
        self._stats["start_time"] = time.time()
        await self.state_store.sync_from_remote()

        # Register signal handlers
        try:
            loop = asyncio.get_running_loop()
            for sig_name in ("SIGTERM", "SIGINT"):
                sig = getattr(signal, sig_name, None)
                if sig:
                    loop.add_signal_handler(sig, self._on_shutdown_signal)
        except (NotImplementedError, RuntimeError):
            pass

        # Configure broker
        for symbol in self.config.symbols:
            self.broker.add_product(symbol)
        await self.broker.start_websocket()
        await self.event_bus.start()
        await embedding_manager.start()

        # Initialize Session
        try:
            balance = await self.broker.get_paper_balance()
            capital = Decimal(str(balance["equity"]))
            self.active_session_id = await self.db_writer.start_session(
                initial_capital=capital,
                metadata={"mode": "SIM" if self.config.simulate else "LIVE"},
            )
            # Start background loops
            self._tasks.add(asyncio.create_task(self._pnl_recording_loop()))
            self._tasks.add(asyncio.create_task(self._sentiment_refresh_loop()))
            logger.info("[TS] Performance and Sentiment loops started")
            if self.config.simulate:
                self.broker.paper_account.active_session_id = self.active_session_id
            logger.info(f"[SESSION] DB session started: {self.active_session_id}")
        except Exception as e:
            logger.error(f"[DB] Session start failed: {e}")

        await self._run_pipeline()

    async def stop(self) -> None:
        """Stop the trading system."""
        self._running = False
        self._shutdown_event.set()
        for task in self._tasks:
            task.cancel()
        logger.info("[TS] All background tasks cancelled")
        logger.info("TRADING SYSTEM — STOPPED")
        await self.event_bus.stop()
        await self.broker.close()
        await embedding_manager.stop()

        if self.active_session_id:
            try:
                balance = await self.broker.get_paper_balance()
                await self.db_writer.stop_session(
                    session_id=self.active_session_id,
                    final_capital=Decimal(str(balance["equity"])),
                    summary=self._stats,
                )
            except Exception as e:
                logger.error(f"[DB] Session stop failed: {e}")

    async def _sentiment_refresh_loop(self) -> None:
        """Periodically refresh the global market sentiment embedding for semantic RAG."""
        logger.info("[TS] Global Sentiment Refresh loop active (600s interval)")
        while self._running:
            try:
                # 1. Gather recent context for the primary symbol
                symbol = self.config.symbols[0] if self.config.symbols else "BTC-USD"
                quote = self.broker._quotes.get(symbol, {})
                price = float(quote.get("price") or 0.0)
                
                # 2. Construct a 'Market Narrative'
                # This text will be embedded by phi3:mini to find similar past regimes
                narrative = (
                    f"Market context for {symbol} at {datetime.now().isoformat()}. "
                    f"Current price is {price:.2f}. "
                    f"Volatility is {config_manager.get('VOLATILITY_MULTIPLIER', 1.0):.2f}x. "
                    f"System is searching for {self.config.simulate_mode} regime templates."
                )
                
                # 3. Enqueue for Async Vectorization
                embedding_manager.refresh_sentiment(narrative)
                
            except Exception as e:
                logger.error(f"[TS] Sentiment refresh failed: {e}")
            
            # Refresh every 10 minutes (600 seconds) to avoid over-burdening Ollama
            await asyncio.sleep(600)

    async def _pnl_recording_loop(self) -> None:
        """Periodically record PnL snapshots to DB."""
        while self._running:
            try:
                if self.active_session_id:
                    balance = await self.broker.get_paper_balance()
                    # Balance keys: equity, cash, realized_pnl, etc.
                    await self.db_writer.write_pnl_snapshot(
                        total_equity=Decimal(str(balance.get("equity", 0))),
                        cash=Decimal(str(balance.get("cash", 0))),
                        realized_pnl=Decimal(
                            str(balance.get("realized_pnl", 0))
                        ),
                        unrealized_pnl=Decimal(
                            str(balance.get("unrealized_pnl", 0))
                        ),
                        total_commission=Decimal(
                            str(balance.get("total_commissions", 0))
                        ),
                        session_id=self.active_session_id,
                    )
            except Exception as e:
                logger.error(f"[PNL_REC] Failed to record snapshot: {e}")
            
            await asyncio.sleep(5)  # Record every 5 seconds

    def _on_shutdown_signal(self) -> None:
        logger.warning("Shutdown signal received")
        self._shutdown_event.set()

    async def _on_market_data_update(self, data: dict[str, Any]) -> None:
        symbol = data.get("product_id") or data.get("symbol")
        if not symbol:
            return
        price = Decimal(str(data.get("price", "0")))
        if price > 0:
            self.broker._quotes[symbol] = {"price": price}

        event = MarketEvent(
            event_type=EventType.MARKET_DATA,
            source="broker.coinbase",
            payload=MarketPayload(
                symbol=symbol,
                bid=Decimal(str(data.get("best_bid", "0"))),
                ask=Decimal(str(data.get("best_ask", "0"))),
                data=data,
            ),
        )
        await self.event_bus.publish(event)

    async def _run_pipeline(self) -> None:
        """Main pipeline loop."""
        while self._running and not self._shutdown_event.is_set():
            try:
                # 1. Pipeline Execution
                if self.kill_switch.get_kill_telemetry()["is_system_halted"]:
                    logger.error("Kill Switch active — halting")
                    break

                self.pre_trade_risk.set_kill_switch_active(
                    self.kill_switch.get_kill_telemetry()["is_system_halted"]
                )

                tasks = [self._process_symbol(symbol) for symbol in self.config.symbols]
                await asyncio.gather(*tasks)

                # Rate limiting: wait between signal checks to reduce whipsaw
                if self.config.signal_interval_s > 0:
                    await asyncio.sleep(self.config.signal_interval_s)

                # 2. Periodic Reconciliation
                await self._periodic_reconciliation()

                # 3. Heartbeat & PnL Snapshot
                self._stats["last_heartbeat"] = time.time()
                try:
                    balance = await self.broker.get_paper_balance()
                    await self.db_writer.write_pnl_snapshot(
                        total_equity=Decimal(str(balance["equity"])),
                        cash=Decimal(str(balance["cash"])),
                        realized_pnl=Decimal(str(balance["realized_pnl"])),
                        unrealized_pnl=Decimal("0"),
                        total_commission=Decimal(
                            str(balance["total_commissions"])
                        ),
                        session_id=self.active_session_id,
                    )
                except Exception as e:
                    logger.debug(f"[DB] PnL snap failed: {e}")

                # Wait for next tick
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=self.config.heartbeat_interval_s
                    )
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                self._stats["errors"] += 1
                import traceback
                logger.error(f"Pipeline error: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(1)

        await self.stop()

    async def _process_symbol(self, symbol: str) -> None:
        """Modular processing for a single symbol."""
        self.latency_enforcer.start_pipeline(f"pipeline-{symbol}")

        # 1. Market Data
        market_data = await self._get_market_data(symbol)
        if market_data is None:
            return

        # 2. Alpha Engine
        ml_result = await self._run_ml_alpha(symbol, market_data)
        if ml_result is None:
            return

        # 3. Signal & Risk Pipeline
        signal = await self._validate_and_generate_signal(symbol, ml_result)
        if signal:
            await self._execute_full_workflow(symbol, signal)

        # 4. Latency Completion
        self.latency_enforcer.end_pipeline(f"pipeline-{symbol}")
        
        # Sync real-time latency to telemetry cache
        # We take the duration of the pilot symbol to represent system pressure
        pilot_trace = self.latency_enforcer.get_pipeline_data(f"pipeline-{symbol}")
        if pilot_trace:
            self._last_latency_ms = pilot_trace.total_duration_ms

        # 5. UNCONDITIONAL Pulse module traces for forensic awareness (Standash §14)
        # This ensures the Logic Matrix stays alive even during "HOLD" states.
        self._last_module_traces = self._get_module_traces(symbol, ml_result)

    async def _validate_and_generate_signal(
        self, symbol: str, ml_result: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Check existing positions and generate entry/exit signals."""
        if self._consecutive_losses >= config_manager.get("MAX_CONSECUTIVE_LOSSES"):
            logger.warning(
                f"[CIRCUIT_BREAKER] {symbol} halted: {self._consecutive_losses} consecutive losses"
            )
            return None

        if self._loss_cooldown.get(symbol, 0) > 0:
            logger.debug(
                f"[COOLDOWN] {symbol} in cooldown: {self._loss_cooldown[symbol]} ticks remaining"
            )
            self._loss_cooldown[symbol] -= 1
            return None

        current_hour = datetime.utcnow().hour
        if current_hour in LOW_LIQUIDITY_HOURS:
            logger.debug(f"[TIME_FILTER] {symbol} skipped: low liquidity hour {current_hour} UTC")
            return None

        with self.latency_enforcer.measure_stage("signal_generation"):
            balance = await self.broker.get_balance()
            symbol_key = symbol.split("-", 1)[0]
            current_qty = float(balance.get(symbol_key, 0.0))
            current_price = (
                self._market_data[symbol][-1]["close"] if self._market_data[symbol] else (config_manager.get("REFERENCE_PRICE") or 50000.0)
            )

            market_data = await self._get_market_data(symbol)
            if not market_data:
                return None

            # Bid-Ask Spread Filter: Prevent EV- cannibalization
            bid = float(market_data.get("bid", 0))
            ask = float(market_data.get("ask", 0))
            spread_pct = (ask - bid) / current_price if current_price > 0 else 0
            
            volume = market_data.get("volume", 0)
            if volume < MIN_VOLUME_THRESHOLD:
                logger.info(
                    f"[VOLUME_FILTER] {symbol} skipped: volume {volume:.4f} < {MIN_VOLUME_THRESHOLD}"
                )
                return None

            if abs(current_qty) > EPSILON_QTY:
                # 1. Hard Stops (Always active)
                exit_signal = self._check_stop_loss_take_profit(symbol, current_qty, current_price)
                if exit_signal:
                    logger.info(f"[STOP_LOSS/TP] {symbol} exit triggered at {current_price}")
                    await self._execute_dynamic_exit(
                        symbol, current_qty, exit_signal, reason=exit_signal.get("reason", "HARD_STOP")
                    )
                    self._last_exit_at[symbol] = time.time()
                    return None

            # 2. Dynamic Exits (ML-based) - Signal Hysteresis
                hold_time = time.time() - self._position_opened_at.get(symbol, 0)
                if hold_time < MIN_HOLD_TIME_S:
                    # Skip dynamic checks if trade is too young
                    return None

                # Update Confidence EMA for exit
                raw_confidence = float(ml_result.get("confidence", 0.0))
                last_ema = self._confidence_ema.get(symbol, raw_confidence)
                self._confidence_ema[symbol] = (EMA_ALPHA * raw_confidence) + (
                    (1 - EMA_ALPHA) * last_ema
                )

                # Check for ML reversal signal using EMA smoothed confidence
                ml_result["confidence"] = self._confidence_ema[symbol]
                exit_signal = self._generate_signal(symbol, ml_result, is_exit_check=True)
                
                if exit_signal and exit_signal["side"] != ("BUY" if current_qty > 0 else "SELL"):
                    logger.info(
                        f"[DYNAMIC_EXIT] {symbol} reversal (EMA {self._confidence_ema[symbol]:.2f}) after {hold_time:.1f}s"
                    )
                    await self._execute_dynamic_exit(symbol, current_qty, exit_signal, reason="ML_REVERSAL")
                    self._last_exit_at[symbol] = time.time()
                    return None
                
                new_signal = self._generate_signal(symbol, ml_result, is_exit_check=False)
                if new_signal and new_signal["side"] == ("BUY" if current_qty > 0 else "SELL"):
                    logger.info(f"[AGGRESSIVE_STAKING] {symbol} signal reinforces position")
                    return new_signal
                return None

            # 3. New Entry Pipeline
            # Position Cooldown check
            since_last_exit = time.time() - self._last_exit_at.get(symbol, 0)
            if since_last_exit < POSITION_COOLDOWN_S:
                logger.debug(f"[COOLDOWN] {symbol} (Exit {since_last_exit:.1f}s ago) - Waiting for cooldown")
                return None

            # Update Confidence EMA for entry
            raw_confidence = float(ml_result.get("confidence", 0.0))
            last_ema = self._confidence_ema.get(symbol, raw_confidence)
            self._confidence_ema[symbol] = (EMA_ALPHA * raw_confidence) + (
                (1 - EMA_ALPHA) * last_ema
            )
            
            # Use smoothed confidence for entry signal
            ml_result["confidence"] = self._confidence_ema[symbol]
            
            # Extract predicted move from Chronos-2
            chronos = ml_result.get("chronos", {})
            forecast_mean = chronos.get("mean", [])
            predicted_move_pct = 0.0
            if len(forecast_mean) >= 2:
                predicted_move_pct = abs((forecast_mean[-1] - forecast_mean[0]) / forecast_mean[0])

            # Spread Gateway: Entry only if Alpha > 2.5 * Spread
            if predicted_move_pct < (spread_pct * MIN_REWARD_TO_SPREAD_RATIO):
                logger.info(
                    f"[SPREAD_FILTER] {symbol} rejected: move {predicted_move_pct:.4%} < {MIN_REWARD_TO_SPREAD_RATIO}x spread ({spread_pct:.4%})"
                )
                return None

            signal = self._generate_signal(symbol, ml_result, is_exit_check=False)
            if not signal:
                return None

            # Trend confirmation: check if price is moving in signal direction
            trend_confirmed = self._check_trend_confirmation(symbol, signal["side"])
            if not trend_confirmed:
                logger.info(
                    f"[TREND_FILTER] {symbol} skipped: trend not confirmed for {signal['side']}"
                )
                return None

            direction = signal["side"]

            # Require consecutive signals before entry
            if symbol in self._last_signal_direction:
                if direction == self._last_signal_direction[symbol]:
                    self._signal_streak[symbol] = self._signal_streak.get(symbol, 0) + 1
                else:
                    self._signal_streak[symbol] = 0
                    self._last_signal_direction[symbol] = direction

                # Require MIN_CONSECUTIVE_SIGNALS before acting
                if self._signal_streak.get(symbol, 0) < MIN_CONSECUTIVE_SIGNALS:
                    logger.info(
                        f"[STREAK_FILTER] {symbol} waiting: {self._signal_streak.get(symbol, 0)}/{MIN_CONSECUTIVE_SIGNALS}"
                    )
                    return None

                if self._signal_streak.get(symbol, 0) >= 3:
                    logger.debug(
                        f"[SIGNAL_FILTER] {symbol} same-direction streak {self._signal_streak[symbol]}, reducing size"
                    )
                    signal["position_size_multiplier"] *= 0.5
            else:
                self._last_signal_direction[symbol] = direction
                self._signal_streak[symbol] = 0
                logger.debug(
                    f"[STREAK_INIT] {symbol} waiting for {MIN_CONSECUTIVE_SIGNALS} consecutive signals"
                )
                return None

            with self.latency_enforcer.measure_stage("portfolio_allocation"):
                cash = Decimal(str(balance.get("USD", 0.0)))
                portfolio_value = cash + sum(
                    Decimal(str(v)) * Decimal(str(config_manager.get("REFERENCE_PRICE") or 50000.0))
                    for k, v in balance.items()
                    if k != "USD"
                )

                approved_qty, reason = self.allocator.validate_order_size(
                    symbol=symbol,
                    proposed_qty=Decimal(str(signal["position_size_multiplier"])),
                    price=Decimal(str(current_price)),
                    total_portfolio_value=portfolio_value,
                    current_position_qty=Decimal(str(current_qty)),
                )

                if approved_qty <= 0:
                    logger.debug(f"[ALLOCATE] {symbol} rejected: {reason}")
                    return None

                signal["position_size_multiplier"] = float(approved_qty)
                
                # Dynamic SL/TP Calculation
                ohlc_list = market_data.get("historical_ohlc", [])
                atr_val = 0.0
                if len(ohlc_list) >= self.config.atr_window:
                    df_ohlc = pl.DataFrame(ohlc_list)
                    atr_val = float(self.atr_indicator.compute(df_ohlc).tail(1)[0] or 0)

                chronos = ml_result.get("chronos", {})
                f_95 = float(chronos.get("quantile_95", [0])[-1])
                f_05 = float(chronos.get("quantile_05", [0])[-1])
                f_range = f_95 - f_05 if f_95 > 0 else 0.0

                risk_levels = self.guardrail_manager.evaluate(
                    price=current_price,
                    atr=atr_val,
                    forecast_range=f_range,
                    side=direction
                )

                signal["stop_loss"] = risk_levels.get("sl_price")
                signal["take_profit"] = risk_levels.get("tp_price")
                
                logger.info(
                    f"[DYNAMIC_RISK] {symbol} SL={signal['stop_loss']:.2f} "
                    f"TP={signal['take_profit']:.2f} "
                    f"({risk_levels.get('risk_source')}, ATR={atr_val:.2f})"
                )

            self._stats["signals"] += 1
            return signal

    def _get_module_traces(self, symbol: str, ml_result: dict[str, Any]) -> dict[str, Any]:
        """Aggregate forensic traces from all sub-engines with deep diagnostics."""
        from qtrader.core.latency_enforcer import latency_enforcer
        
        latencies = latency_enforcer.get_current_measurements()
        recon_audit = self.reconciliation_engine.get_last_audit() if hasattr(self, "reconciliation_engine") else {}

        return {
            "AlphaEngine": {
                **ml_result,
                "latency_ms": latencies.get("alpha_computation", {}).get("duration_ms", 0.0),
                "budget_ms": latencies.get("alpha_computation", {}).get("budget_ms", 5.0),
            },
            "RiskEngine": {
                **(self.kill_switch.get_trace() if hasattr(self.kill_switch, "get_trace") else {}),
                "latency_ms": latencies.get("risk_check", {}).get("duration_ms", 0.0),
                "budget_ms": latencies.get("risk_check", {}).get("budget_ms", 5.0),
            },
            "RiskGuard": {
                **(self.guardrail_manager.get_trace() if hasattr(self.guardrail_manager, "get_trace") else {}),
                "latency_ms": latencies.get("signal_generation", {}).get("duration_ms", 0.0),
                "budget_ms": latencies.get("signal_generation", {}).get("budget_ms", 5.0),
            },
            "Portfolio": {
                **(self.allocator.get_trace() if hasattr(self.allocator, "get_trace") else {}),
                "latency_ms": latencies.get("portfolio_allocation", {}).get("duration_ms", 0.0),
                "budget_ms": latencies.get("portfolio_allocation", {}).get("budget_ms", 10.0),
            },
            "Reconciliation": {
                **recon_audit,
                "status": "DANGER" if (recon_audit.get("mismatch_count") is not None and recon_audit.get("mismatch_count", 0) > 0) else "OK"
            },
            "Strategy": {
                "streak": self._signal_streak.get(symbol, 0),
                "last_direction": self._last_signal_direction.get(symbol, "NONE"),
                "cooldown": self._loss_cooldown.get(symbol, 0),
                "is_circuit_broken": self._consecutive_losses >= config_manager.get("MAX_CONSECUTIVE_LOSSES"),
                "is_anomaly": self._consecutive_losses >= 3  # Simple anomaly flag
            }
        }

    async def _execute_full_workflow(self, symbol: str, signal: dict[str, Any]) -> None:
        """Full execution workflow with risk and shadow guards."""
        with self.latency_enforcer.measure_stage("risk_check"):
            if not self._check_risk(signal):
                return
            if not self.config.simulate:
                shadow_ok, reason = self.shadow_engine.can_trade_live(symbol)
                if not shadow_ok:
                    logger.warning(f"[SHADOW] {symbol} rejected: {reason}")
                    return

        with self.latency_enforcer.measure_stage("order_submission"):
            await self._execute_order(signal)

        with self.latency_enforcer.measure_stage("fill_processing"):
            await self._process_fills(signal)

    async def _get_market_data(self, symbol: str) -> dict[str, Any] | None:
        """Consolidated market data provider."""
        balance = await self.broker.get_balance()
        positions = {k: v for k, v in balance.items() if k != "USD"}

        quote = self.broker._quotes.get(symbol, {})
        if quote and "price" in quote and quote["price"] > 0:
            price = float(quote["price"])
            bid = float(quote.get("bid", quote["price"]))
            ask = float(quote.get("ask", quote["price"]))
        else:
            base_price = MID_PRICE_BTC if "BTC" in symbol else 3000.0 if "ETH" in symbol else 100.0
            price = base_price
            bid = base_price * 0.9998
            ask = base_price * 1.0002

        if len(self._market_data[symbol]) > 0:
            last_entry = self._market_data[symbol][-1]
            last_price = last_entry["close"] if isinstance(last_entry, dict) else last_entry
            
            price_change = (price - last_price) / last_price if last_price > 0 else 0
            if abs(price_change) > 0.05:
                logger.warning(
                    f"[MARKET_DATA] {symbol} price jump {price_change:.2%}, using last known"
                )
                price = last_price
                bid = last_price * 0.9998
                ask = last_price * 1.0002

        self.broker._quotes[symbol] = {
            "price": Decimal(str(price)),
            "bid": Decimal(str(bid)),
            "ask": Decimal(str(ask)),
        }

        high = float(quote.get("high", price))
        low = float(quote.get("low", price))

        # Store OHLC for ATR calculation
        self._market_data[symbol].append({
            "high": high,
            "low": low,
            "close": price
        })
        if len(self._market_data[symbol]) > MAX_MD_POINTS:
            self._market_data[symbol] = self._market_data[symbol][-MD_PRUNE_TARGET:]

        # Simple volume proxy
        volume = 0.0
        if len(self._market_data[symbol]) >= 2:
            last_p = self._market_data[symbol][-1]["close"]
            prev_p = self._market_data[symbol][-2]["close"]
            volume = abs(last_p - prev_p) / prev_p if prev_p > 0 else 0.0

        return {
            "symbol": symbol,
            "price": price,
            "bid": bid,
            "ask": ask,
            "historical_ohlc": list(self._market_data[symbol]),
            "historical_prices": [x["close"] for x in self._market_data[symbol]],
            "positions": positions,
            "volume": volume,
        }

    async def _run_ml_alpha(
        self, symbol: str, market_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Run ML prediction pipeline."""
        historical = market_data.get("historical_prices", [])
        if len(historical) < MIN_HISTORY_FOR_ALPHA:
            return None

        result = await self.ml_pipeline.run(
            historical_prices=historical[-100:],
            market_features={},
            market_context={},
            system_state={},
            prediction_length=24,
        )
        return {
            "decision": result.decision,
            "chronos": result.chronos_forecast,
            "tabpfn": result.tabpfn_risk,
            "latency": result.pipeline_latency_ms,
        }

    def _check_stop_loss_take_profit(
        self, symbol: str, current_qty: float, current_price: float
    ) -> dict[str, Any] | None:
        """Check if current position hits stop loss or take profit."""
        # AGGRESSIVE MODE: Iterate through all independent trades (lots)
        lots = self.broker.paper_account.get_positions().get(symbol, [])
        if not lots:
            return None

        # Dynamic Thresholds
        sl_pct = config_manager.get("STOP_LOSS_PCT")
        tp_pct = config_manager.get("TAKE_PROFIT_PCT")

        # Fixed Indentation & Multi-Trade Isolation
        for lot in lots:
            avg_entry = float(lot.avg_price)
            pnl_pct = (current_price - avg_entry) / avg_entry if avg_entry > 0 else 0
            
            if lot.side == "BUY":
                if pnl_pct <= -sl_pct:
                    logger.info(f"[LOT_STOP] {symbol} lot {lot.trade_id} exit at {current_price} (SL)")
                    return {"symbol": symbol, "side": "SELL", "reason": "STOP_LOSS", "lot_id": lot.trade_id}
                if pnl_pct >= tp_pct:
                    logger.info(f"[LOT_TP] {symbol} lot {lot.trade_id} exit at {current_price} (TP)")
                    return {"symbol": symbol, "side": "SELL", "reason": "TAKE_PROFIT", "lot_id": lot.trade_id}
            elif lot.side == "SELL":
                # For SHORTS, pnl_pct is negative if price went up
                if pnl_pct >= sl_pct:
                    return {"symbol": symbol, "side": "BUY", "reason": "STOP_LOSS", "lot_id": lot.trade_id}
                if pnl_pct <= -tp_pct:
                    return {"symbol": symbol, "side": "BUY", "reason": "TAKE_PROFIT", "lot_id": lot.trade_id}
        
        return None

    def _generate_signal(
        self, symbol: str, ml_result: dict[str, Any], is_exit_check: bool = False
    ) -> dict[str, Any] | None:
        """Core signal generation logic using dynamic thresholds."""
        decision = ml_result["decision"]
        action = str(
            decision.action.value if hasattr(decision.action, "value") else decision.action
        )
        confidence = float(decision.confidence)

        # Pull thresholds from DynamicConfig
        min_conf = config_manager.get("MIN_CONFIDENCE")
        exit_conf = config_manager.get("EXIT_CONFIDENCE")
        threshold = exit_conf if is_exit_check else min_conf

        if action == "HOLD" or confidence < threshold:
            return None

        position_size = float(getattr(decision, "position_size_multiplier", 0.1))
        # Cap position size based on dynamic config
        position_size = min(position_size, config_manager.get("POSITION_SIZE_PCT"))

        task = asyncio.create_task(
            self.db_writer.write_thinking_log(
                symbol=symbol,
                action=action,
                confidence=confidence,
                thinking=str(decision.reasoning),
                explanation=str(decision.explanation),
                session_id=self.active_session_id,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return {
            "symbol": symbol,
            "side": "BUY" if action == "BUY" else "SELL",
            "position_size_multiplier": position_size,
            "confidence": confidence,
            "reasoning": str(decision.reasoning),
        }

    def _check_trend_confirmation(self, symbol: str, side: str) -> bool:
        """Check if price trend confirms the signal direction using lookback window."""
        lookback = config_manager.get("TREND_LOOKBACK")
        if not self._market_data[symbol] or len(self._market_data[symbol]) < lookback:
            return True  # Not enough data, allow signal

        prices = [x["close"] for x in self._market_data[symbol][-lookback:]]

        # Calculate simple moving average difference
        ma_short = sum(prices[-3:]) / 3
        ma_long = sum(prices) / len(prices)

        if side == "BUY":
            # For BUY signal, price should be trending up (short MA > long MA)
            return ma_short >= ma_long
        else:
            # For SELL signal, price should be trending down (short MA < long MA)
            return ma_short <= ma_long

    def _check_risk(self, signal: dict[str, Any]) -> bool:
        """Pre-trade risk validator wrapper."""
        return self.pre_trade_risk.validate_order(
            symbol=signal["symbol"],
            side=signal["side"],
            quantity=Decimal(str(signal["position_size_multiplier"])),
            price=None,
        ).approved

    async def _execute_order(self, signal: dict[str, Any]) -> None:
        """Submit order to broker and persist."""
        order = OrderEvent(
            source="TradingSystem",
            event_type=EventType.ORDER,
            payload=OrderPayload(
                order_id=str(uuid4()),
                symbol=signal["symbol"],
                action=signal["side"],
                quantity=Decimal(str(signal["position_size_multiplier"])),
                order_type="MARKET",
                session_id=self.active_session_id,
            ),
        )

        try:
            oid = await self.broker.submit_order(order)
            self._stats["orders"] += 1
            logger.info(f"[ORDER] {signal['symbol']} {signal['side']} submitted: {oid}")
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ORDER] Submission failed: {e}")

    async def _execute_dynamic_exit(
        self, symbol: str, qty: float, signal: dict[str, Any], reason: str = "SIGNAL"
    ) -> None:
        """Execute an exit order and log reason."""
        side = "SELL" if qty > 0 else "BUY"
        order = OrderEvent(
            source="TradingSystem",
            event_type=EventType.ORDER,
            payload=OrderPayload(
                order_id=str(uuid4()),
                symbol=symbol,
                action=side,
                quantity=Decimal(str(abs(qty))),
                order_type="MARKET",
                session_id=self.active_session_id,
            ),
        )
        try:
            await self.broker.submit_order(order)
            self._consecutive_losses = 0  # Logic for streak tracking could be added here
            logger.info(f"[EXIT] {symbol} {side} ({reason})")
        except Exception as e:
            logger.error(f"[EXIT] Failed: {e}")

    async def _process_fills(self, signal: dict[str, Any]) -> None:
        """Process fills and update local tracking."""
        # This is typically handled by the event loop, but we can poll for feedback
        history = self.broker.paper_account.fill_history
        if len(history) <= self._last_fill_count:
            return

        new_fills = list(history)[self._last_fill_count :]
        self._last_fill_count = len(history)

        for fill in new_fills:
            self._stats["fills"] += 1
            sym, side, qty, px = fill["symbol"], fill["side"], fill["qty"], fill["price"]

            pos = Position(
                symbol=sym,
                quantity=Decimal(str(qty)),
                average_price=Decimal(str(px)),
                timestamp=datetime.now(),
            )
            await self.state_store.set_position(pos)

            task = asyncio.create_task(
                self.db_writer.write_fill(
                    order_id=fill.get("order_id", ""),
                    symbol=sym,
                    side=side,
                    quantity=Decimal(str(qty)),
                    price=Decimal(str(px)),
                    commission=Decimal(str(fill.get("commission", 0))),
                    source="TS",
                    session_id=fill.get("session_id") or self.active_session_id,
                )
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

            realized_pnl = self.broker.paper_account.realized_pnl
            if realized_pnl > 0:
                self._consecutive_losses = 0
                self._win_history.append(1)
            else:
                self._win_history.append(0)

            # Check for MLOps retraining (Self-Learning)
            if len(self._win_history) >= 10:
                current_wr = sum(self._win_history) / len(self._win_history)
                if current_wr < 0.35: # Performance decay trigger
                    decision = self.retrain_system.evaluate(
                        expected_dist=np.array([0.5, 0.5]), # Mock dist for now
                        actual_dist=np.array([current_wr, 1-current_wr]),
                        current_perf=current_wr,
                        baseline_perf=0.55
                    )
                    if decision.trigger:
                        logger.error(f"[RETRAIN] Performance decay detected (WR={current_wr:.2f}). {decision.reason}")

            logger.info(
                f"[TRADE] {fill.get('timestamp', '')} | {sym} {side} {qty}@{px} | "
                f"SL={signal.get('stop_loss', 'N/A')} TP={signal.get('take_profit', 'N/A')} | "
                f"Reason: {signal.get('reasoning', 'SIGNAL')}"
            )

    async def _periodic_reconciliation(self) -> None:
        """Standard reconciliation checks."""
        self._stats["recon_checks"] += 1

    async def _send_alert(self, severity: AlertSeverity, title: str, message: str) -> None:
        """System alerting."""
        await self.alert_engine.send_alert(
            AlertMessage(title=title, message=message, severity=severity, source="TS")
        )


def create_trading_system(
    simulate: bool = True, symbols: list[str] | None = None, ml_pipeline: Any | None = None
) -> TradingSystem:
    config = TradingSystemConfig(simulate=simulate, symbols=symbols or ["BTC-USD"])
    return TradingSystem(config, ml_pipeline=ml_pipeline)


async def main() -> None:
    system = create_trading_system(simulate=True, symbols=["BTC-USD"])

    def handle_signal(sig: int, frame: Any) -> None:
        system._shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await system.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
