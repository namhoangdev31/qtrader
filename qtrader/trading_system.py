"""Unified Trading System — Optimized & Fragmented Orchestration.

Wires together specialized sub-engines:
  Market Data → Alpha (Atomic Trio ML) → Strategy (SignalEngine) → Risk → Order
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import numpy as np
import polars as pl
from loguru import logger

from qtrader.analytics.forensic_tracer import ForensicTracer
from qtrader.analytics.pnl_attribution import PnLAttributionEngine
from qtrader.core.config import settings
from qtrader.core.dynamic_config import config_manager
from qtrader.core.event_bus import EventBus
from qtrader.core.trace_authority import TraceAuthority
from qtrader.core.events import (
    EventType,
    MarketEvent,
    MarketPayload,
    OrderEvent,
    OrderPayload,
    RiskRejectedEvent,
    RiskRejectedPayload,
)
from qtrader.core.latency_enforcer import LatencyEnforcer, latency_enforcer
from qtrader.core.state_store import Position, StateStore
from qtrader.core.session_state import SessionState
from qtrader.core.lifecycle_tasks import LifecycleTaskManager
from qtrader.execution.brokers.coinbase import CoinbaseBrokerAdapter
from qtrader.execution.pre_trade_risk import PreTradeRiskConfig, PreTradeRiskValidator
from qtrader.execution.reconciliation_engine import ReconciliationEngine
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.features.technical.volatility import ATRFeature
from qtrader.ml.atomic_trio import AtomicTrioPipeline
from qtrader.ml.embedding_worker import embedding_manager
from qtrader.ml.remote_client import RemoteAtomicTrioPipeline
from qtrader.ml.retrain_system import RetrainSystem
from qtrader.monitoring.alert_engine import AlertEngine, AlertMessage, AlertSeverity
from qtrader.oms.order_management_system import UnifiedOMS
from qtrader.persistence.db_writer import TradeDBWriter
from qtrader.portfolio.allocator import CapitalAllocationEngine
from qtrader.risk.dynamic_guardrail import DynamicGuardrailManager
from qtrader.risk.kill_switch import GlobalKillSwitch
from qtrader.strategy.manager import StrategyManager
from qtrader.strategy.signal_engine import SignalEngine
from qtrader.oms.oms_adapter import ExecutionOMSAdapter
from qtrader.core.types import AllocationWeights, RiskMetrics
from qtrader.core.forensic_auditor import ForensicAuditor

@dataclass
class TradingSystemConfig:
    """Configuration for the Trading System (Legacy Wrapper for QTraderSettings)."""
    simulate: bool = settings.simulate_mode
    symbols: list[str] = field(default_factory=lambda: settings.trading_symbols)
    max_position_usd: float = field(default_factory=lambda: config_manager.get("position_size_pct") * settings.starting_equity)
    max_drawdown_pct: float = field(default_factory=lambda: config_manager.get("max_drawdown_limit"))
    max_order_qty: float = settings.ts_max_order_qty
    max_order_notional: float = settings.ts_max_order_notional
    max_orders_per_second: float = field(default_factory=lambda: config_manager.get("ts_max_orders_per_second"))
    forecast_model_id: str = settings.ts_forecast_model
    risk_model_id: str = settings.ts_risk_model
    decision_model_id: str = settings.ts_decision_model
    
    recon_interval_s: float = 60.0
    heartbeat_interval_s: float = 10.0
    reference_price: float = settings.ts_reference_price

class TradingSystem:
    """Unified Trading System — Complete End-to-End Orchestrator."""

    def __init__(
        self, config: TradingSystemConfig | None = None, ml_pipeline: Any | None = None
    ) -> None:
        self.config = config or TradingSystemConfig()
        self.state_store = StateStore()
        self.event_bus = EventBus(redis_url=os.getenv("REDIS_URL"))        
        self.session_state = SessionState()
        self.tracer = ForensicTracer()
        self.signal_engine = SignalEngine(self.session_state)
        
        if ml_pipeline is not None:
            self.ml_pipeline = ml_pipeline
        else:
            ml_url = os.environ.get("ML_ENGINE_URL")
            if ml_url:
                self.ml_pipeline = RemoteAtomicTrioPipeline(base_url=ml_url)
            else:
                self.ml_pipeline = AtomicTrioPipeline(
                    forecast_model_id=self.config.forecast_model_id,
                    risk_model_id=self.config.risk_model_id,
                    decision_model_id=self.config.decision_model_id,
                )

        self.retrain_system = RetrainSystem(psi_threshold=0.20, performance_drop_delta=0.15)
        self.kill_switch = GlobalKillSwitch(
            dd_limit=self.config.max_drawdown_pct,
            loss_limit=self.config.max_position_usd * 2,
            auto_liquidate=False,
        )
        self.pre_trade_risk = PreTradeRiskValidator(
            PreTradeRiskConfig(
                max_order_quantity=Decimal(str(self.config.max_order_qty)),
                max_order_notional=Decimal(str(self.config.max_order_notional)),
                max_position_per_symbol=Decimal(str(self.config.max_position_usd / self.config.reference_price)),
                max_position_usd=Decimal(str(self.config.max_position_usd)),
                max_orders_per_second=int(self.config.max_orders_per_second),
            )
        )
        self.broker = CoinbaseBrokerAdapter(simulate=self.config.simulate, kill_switch=self.kill_switch)
        self.broker.set_market_data_handler(self._on_market_data_update)

        self.oms = UnifiedOMS(state_store=self.state_store, event_bus=self.event_bus)
        
        self.oms_adapter = ExecutionOMSAdapter(
            exchange_adapters={"coinbase": self.broker},
            oms=self.oms,
            routing_mode="smart",
            name="MainExecutionOMSAdapter"
        )
        
        self.allocator = CapitalAllocationEngine(max_cap=Decimal("0.2"))
        self.guardrail_manager = DynamicGuardrailManager()
        self.atr_indicator = ATRFeature(window=settings.ts_atr_window)
        
        self.recon = ReconciliationEngine(
            event_bus=self.event_bus, oms=self.oms, state_store=self.state_store,
            recon_interval_s=self.config.recon_interval_s, kill_switch=self.kill_switch,
        )
        self.alert_engine = AlertEngine()
        self.latency_enforcer = LatencyEnforcer(fail_on_breach=False)
        self.db_writer = TradeDBWriter()
        self.strategy_manager = StrategyManager(symbol=self.config.symbols[0])
        
        self.lifecycle = LifecycleTaskManager(self.broker, self.db_writer, self.config.symbols)
        self.auditor = ForensicAuditor(self.event_bus, self.db_writer)

        self._running = False
        self._shutdown_event = asyncio.Event()
        self._market_data: dict[str, list[dict[str, float]]] = {s: [] for s in self.config.symbols}
        self._stats = {"orders": 0, "fills": 0, "errors": 0, "signals": 0, "start_time": 0.0}
        self._last_fill_count: int = 0
        self._tasks: set[asyncio.Task[Any]] = set()
        self.last_latency_ms: float = 0.0
        self._last_module_traces: dict[str, Any] = {}

    @property
    def active_session_id(self) -> str | None:
        return self.session_state.session_id

    @active_session_id.setter
    def active_session_id(self, value: str | None) -> None:
        self.session_state.session_id = value

    def get_status(self) -> dict[str, Any]:
        return {
            "status": "RUNNING" if self._running else "IDLE",
            "session_id": self.active_session_id,
            "market_price": self.config.reference_price,
            "latency_ms": round(self.last_latency_ms, 2),
            "stats": self._stats,
            "module_traces": self._last_module_traces,
            "uptime": round(time.time() - self._stats["start_time"], 2) if self._running else 0.0,
        }

    async def start(self) -> None:
        logger.info("[TS] STARTING Unified Orchestrator")
        self._running = True
        self._stats["start_time"] = time.time()
        
        for symbol in self.config.symbols:
            self.broker.add_product(symbol)
        await self.broker.start_websocket()
        await self.event_bus.start()
        await embedding_manager.start()
        await self.oms_adapter.start()
        
        balance = await self.broker.get_paper_balance()
        self.session_state.session_id = await self.db_writer.start_session(
            initial_capital=Decimal(str(balance["equity"])),
            metadata={"mode": "SIM" if self.config.simulate else "LIVE"},
        )
        
        self.lifecycle.is_running = True
        self.auditor.session_id = self.active_session_id
        if settings.ENABLE_AUTO_FORENSIC:
            self.auditor.start()
            
        self._tasks.add(asyncio.create_task(self.lifecycle.sentiment_refresh_loop(self.config.simulate)))
        self._tasks.add(asyncio.create_task(self.lifecycle.pnl_recording_loop(self.active_session_id)))
        self._tasks.add(asyncio.create_task(self.lifecycle.health_logging_loop(self.active_session_id, self)))
        
        self._tasks.add(asyncio.create_task(self._run_pipeline()))

    async def stop(self) -> None:
        self._running = False
        self.lifecycle.is_running = False
        self.auditor.stop()
        self._shutdown_event.set()
        for t in self._tasks: t.cancel()
        await self.event_bus.stop()
        await self.broker.close()
        await embedding_manager.stop()
        await self.oms_adapter.stop()
        
        if self.active_session_id:
            balance = await self.broker.get_paper_balance()
            await self.db_writer.stop_session(self.active_session_id, Decimal(str(balance["equity"])), self._stats)

    async def _on_market_data_update(self, data: dict[str, Any]) -> None:
        symbol = data.get("product_id") or data.get("symbol")
        price = Decimal(str(data.get("price", "0")))
        bid = Decimal(str(data.get("best_bid", "0")))
        ask = Decimal(str(data.get("best_ask", "0")))
        if price > 0 and symbol:
            self.broker._quotes[symbol] = {"price": price}
            self.config.reference_price = float(price)
            from qtrader.core.config import settings
            old_ref = settings.ts_reference_price
            settings.ts_reference_price = float(price)
            config_manager.update("current_market_price", float(price))
            self.pre_trade_risk.update_mid_price(symbol, price)
            if abs(float(price) - old_ref) / old_ref > 0.01:
                logger.info(f"[TS] Reference Price shifted > 1%: {old_ref:.2f} -> {price:.2f}")

            try:
                await self.event_bus.publish(
                    MarketEvent(
                        source="coinbase_ws",
                        payload=MarketPayload(
                            symbol=symbol,
                            price=price,
                            data=data,
                            bid=bid,
                            ask=ask,
                        ),
                    )
                )
            except Exception as e:
                logger.debug(f"[TS] Failed to publish MarketEvent: {e}")
        
        if self.active_session_id:
            await self.db_writer.write_raw_market_data(
                symbol=symbol, last_price=price, session_id=self.active_session_id,
                bid=bid, ask=ask,
                volume=Decimal(str(data.get("volume_24h", "0")))
            )

    async def _run_pipeline(self) -> None:
        while self._running and not self._shutdown_event.is_set():
            try:
                tasks = [self._process_symbol(s) for s in self.config.symbols]
                await asyncio.gather(*tasks)
                await asyncio.sleep(config_manager.get("SIGNAL_INTERVAL_S", 1.0))
            except Exception as e:
                logger.error(f"[PIPELINE] Fatal: {e}")
                await asyncio.sleep(1)

    async def _process_symbol(self, symbol: str) -> None:
        with TraceAuthority.inject_trace():
            self.latency_enforcer.start_pipeline(f"pipeline-{symbol}")
            
            market_data = await self._get_market_data(symbol)
            ml_result = await self._run_ml_alpha(symbol, market_data)
            
            if ml_result:
                positions = self.broker.paper_account.get_positions().get(symbol, [])
                exit_signal = self.signal_engine.check_exit_triggers(
                    symbol, market_data["price"], positions, 
                    settings.ts_min_sl_pct, settings.ts_max_sl_pct
                )
                
                if exit_signal:
                    await self._execute_exit(symbol, exit_signal)
                else:
                    signal = self.signal_engine.generate_signal(symbol, ml_result)
                    if signal and self.signal_engine.check_trend_confirmation(symbol, signal["side"], self._market_data[symbol]):
                        risk_result = self.pre_trade_risk.validate_order(
                            symbol, signal["side"], Decimal(str(signal["position_size_multiplier"]))
                        )
                        if risk_result.approved:
                            await self._execute_order(signal)
                        else:
                            # [FORENSIC] Emit RiskRejectedEvent for auditor visibility
                            await self.event_bus.publish(
                                RiskRejectedEvent(
                                    source="TradingSystem",
                                    payload=RiskRejectedPayload(
                                        order_id=f"REJECTED-{uuid4()}",
                                        reason=risk_result.reason,
                                        metric_value=0.0, # detailed metrics omitted for brevity
                                        threshold=0.0,
                                        metadata={"checks_failed": risk_result.checks_failed}
                                    )
                                )
                            )
    
            self.latency_enforcer.end_pipeline(f"pipeline-{symbol}")
        trace = self.latency_enforcer.get_pipeline_data(f"pipeline-{symbol}")
        if trace: self.last_latency_ms = trace.total_latency_ms
        
        self._last_module_traces = self.tracer.aggregate_traces(
            symbol, ml_result or {}, self.broker._quotes, self.kill_switch, 
            self.guardrail_manager, self.allocator, self.recon, self.session_state
        )
        
        from qtrader.core.events import DecisionTraceEvent, DecisionTracePayload
        await self.event_bus.publish(
            DecisionTraceEvent(
                source="TradingSystem",
                payload=DecisionTracePayload(
                    model_id=f"TradingSystem-{symbol}",
                    features={},
                    signal=Decimal("0"),
                    decision_price=Decimal(str(market_data["price"])),
                    decision="HEARTBEAT" if not ml_result else "PIPELINE_COMPLETE",
                    config_version=1,
                    module_traces=self._last_module_traces
                )
            )
        )

    async def _get_market_data(self, symbol: str) -> dict[str, Any]:
        quote = self.broker._quotes.get(symbol) or \
                self.broker._quotes.get(symbol.replace("-", "/")) or \
                self.broker._quotes.get(symbol.replace("/", "-")) or {}
        
        from qtrader.core.config import settings
        price = float(quote.get("price") or settings.ts_reference_price)
        
        self._market_data[symbol].append({"close": price})
        if len(self._market_data[symbol]) > 1000: self._market_data[symbol].pop(0)
        
        return {
            "symbol": symbol, "price": price, 
            "historical_ohlc": list(self._market_data[symbol]),
            "historical_prices": [x["close"] for x in self._market_data[symbol]]
        }

    async def _run_ml_alpha(self, symbol: str, market_data: dict[str, Any]) -> dict[str, Any] | None:
        hist = market_data["historical_prices"]
        if len(hist) < 20: return None
        res = await self.ml_pipeline.run(historical_prices=hist[-100:])
        return {"decision": res.decision, "chronos": res.chronos_forecast, "tabpfn": res.tabpfn_risk}

    async def _execute_order(self, signal: dict[str, Any]) -> None:
        symbol = signal["symbol"]
        qty = Decimal(str(signal["position_size_multiplier"]))
        
        account = await self.broker.get_paper_balance()
        equity = Decimal(str(account.get("equity", self.config.max_position_usd)))
        
        weight = qty / equity if equity > 0 else Decimal("0")
        
        weights = AllocationWeights(
            timestamp=datetime.now(),
            weights={symbol: weight},
            trace_id=str(uuid4())
        )
        
        risk = RiskMetrics(
            timestamp=datetime.now(),
            portfolio_var=Decimal("0.02"), 
            portfolio_volatility=Decimal("0.01"),
            max_drawdown=Decimal(str(self.config.max_drawdown_pct)),
            leverage=Decimal("1.0"),
            trace_id=weights.trace_id
        )

        await self.oms_adapter.create_order(weights, risk)
        
        self._stats["orders"] += 1

    async def _execute_exit(self, symbol: str, signal: dict[str, Any]) -> None:
        await self._execute_order(signal)
        self.session_state.record_win(symbol)

def create_trading_system(
    simulate: bool = True, 
    symbols: list[str] | None = None, 
    ml_pipeline: Any | None = None
) -> TradingSystem:
    """Factory function to create and configure a TradingSystem instance."""
    config = TradingSystemConfig(
        simulate=simulate,
        symbols=symbols or settings.trading_symbols
    )
    return TradingSystem(config=config, ml_pipeline=ml_pipeline)

if __name__ == "__main__":
    system = TradingSystem()
    asyncio.run(system.start())
