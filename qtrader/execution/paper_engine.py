from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from qtrader.core.config import settings
from qtrader.core.dynamic_config import DynamicSettingsMixin, config_manager
from qtrader.core.events import ForensicNoteEvent, ForensicNotePayload
from qtrader.core.trace_authority import TraceAuthority
from qtrader.execution.paper_mixins import (
    FillMixin,
    PersistenceMixin,
    PositionMixin,
    SignalMixin,
)
from qtrader.execution.paper_models import AdaptiveConfig, OpenPosition, TradeRecord

_LOG = logging.getLogger("qtrader.paper")


class PaperTradingEngine(
    DynamicSettingsMixin, SignalMixin, PositionMixin, FillMixin, PersistenceMixin
):
    """Event-Driven Simulation Engine with institutional-grade forensics.

    Provides high-fidelity execution simulation including slippage,
    latency, and technical signal generation.
    """

    def __init__(  # noqa: PLR0913
        self,
        starting_capital: float = 100000.0,
        performance_fee: float = 0.2,
        max_concurrent_positions: int = 10,
        max_trades_history: int = 1000,
        sl_pct: float = 0.02,
        tp_pct: float = 0.03,
        tick_interval: float = 0.2,
        base_price: float | None = None,
        db_writer: Any | None = None,
        session_id: str | None = None,
    ) -> None:
        self._db_writer = db_writer
        self._session_id = session_id

        self.starting_capital = starting_capital
        self.performance_fee = performance_fee
        self.max_concurrent_positions = max_concurrent_positions
        self.closed_trades: list[TradeRecord] = []
        self._last_recorded_equity: float | None = None
        self._trade_history = self.closed_trades
        self._max_trades_history = max_trades_history

        self._open_positions: dict[str, list[OpenPosition]] = {}
        self._managed_positions: dict[str, list[OpenPosition]] = {}

        self.adaptive = AdaptiveConfig(
            base_stop_loss_pct=sl_pct,
            base_take_profit_pct=tp_pct,
        )

        ref_price = base_price if base_price is not None else settings.ts_reference_price
        self._cash = starting_capital
        self._total_commissions = 0.0
        self._total_gross_pnl = 0.0
        self._peak_equity = starting_capital
        self._max_drawdown = 0.0
        self._current_price = ref_price
        self._base_price = ref_price
        self._price_history: list[float] = []
        self._volatility = 0.0003
        self._running = False
        self._tick_interval = tick_interval
        self._last_external_tick = 0.0
        self._start_time = time.time()
        self._last_latency_ms = 0.0
        self._last_thinking = "Awaiting first analysis..."
        self._last_explanation = "Simulation engine is initializing market data buffer..."
        self._thinking_history: list[dict[str, Any]] = []

        self._last_trace: dict[str, Any] = {
            "module_traces": {
                "ingestion": {"status": "INITIALIZING", "price": ref_price},
                "AlphaEngine": {"status": "INITIALIZING"},
                "alpha": {"status": "INITIALIZING", "indicators": {"rsi": 50.0}},
                "RiskEngine": {"status": "INITIALIZING"},
                "RiskGuard": {"status": "INITIALIZING"},
                "risk": {"status": "INITIALIZING", "initial_stop_loss": 0.0},
                "Portfolio": {"status": "INITIALIZING"},
                "execution": {"status": "AWAITING", "slippage_bps": 0.0},
                "Reconciliation": {"status": "AWAITING"},
                "Strategy": {"status": "AWAITING"},
            }
        }
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._tick_count = 0

    def add_update_listener(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a new listener for real-time simulation updates."""
        if handler not in self._listeners:
            self._listeners.append(handler)

    def set_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Legacy support for a single handler (maps to listener list)."""
        self.add_update_listener(handler)

    def _emit(self, data: dict[str, Any]) -> None:
        """Notify all registered listeners of a new simulation snapshot."""
        for listener in self._listeners:
            try:
                listener(data)
            except Exception as e:
                _LOG.error(f"[PAPER] Update listener error: {e}")

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def equity(self) -> float:
        market_value = 0.0
        for lots in self._open_positions.values():
            for lot in lots:
                if lot.qty > 0:
                    market_value += lot.qty * self._current_price
                elif lot.qty < 0:
                    notional = abs(lot.qty) * lot.avg_price
                    pnl = (lot.avg_price - self._current_price) * abs(lot.qty)
                    market_value += notional + pnl
        return self._cash + market_value

    @property
    def realized_pnl(self) -> float:
        market_value = 0.0
        notional_value = 0.0
        for lots in self._open_positions.values():
            for lot in lots:
                notional_value += abs(lot.qty) * lot.avg_price
                if lot.qty > 0:
                    market_value += lot.qty * self._current_price
                else:
                    pnl = (lot.avg_price - self._current_price) * abs(lot.qty)
                    market_value += (abs(lot.qty) * lot.avg_price) + pnl

        unrealized_gross = market_value - notional_value
        total_pnl = self.equity - self.starting_capital
        return total_pnl - unrealized_gross

    @property
    def trade_history(self) -> list[TradeRecord]:
        return self.closed_trades

    @property
    def total_commissions(self) -> float:
        return self._total_commissions

    def _build_snapshot(self) -> dict[str, Any]:
        eq = self.equity
        realized = self.realized_pnl
        return {
            "type": "simulation_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "live_config": config_manager.get_all_live(),
            "equity": round(eq, 2),
            "cash": round(self._cash, 2),
            "realized_pnl": round(realized, 2),
            "total_commissions": round(self._total_commissions, 4),
            "total_gross_pnl": round(self._total_gross_pnl, 2),
            "current_price": round(self._current_price, 2),
            "ai_thinking": self._last_thinking,
            "ai_explanation": self._last_explanation,
            "thinking_history": self._thinking_history,
            "live_trace": self._last_trace,
            "base_price": self._base_price,
            "positions": [
                {
                    "symbol": sym,
                    "side": lot.side,
                    "quantity": abs(lot.qty),
                    "entry_price": lot.avg_price,
                    "current_price": self._current_price,
                    "unrealized_pnl": round(
                        (self._current_price - lot.avg_price) * abs(lot.qty)
                        if (lot.qty > 0 or lot.side == "BUY")
                        else (lot.avg_price - self._current_price) * abs(lot.qty),
                        2,
                    ),
                    "unrealized_pnl_pct": round(
                        ((self._current_price - lot.avg_price) / lot.avg_price * 100)
                        if lot.avg_price > 0
                        else 0,
                        2,
                    ),
                    "stop_loss": lot.stop_loss,
                    "take_profit": lot.take_profit,
                    "entry_time": lot.entry_time,
                }
                for sym, lots in self._open_positions.items()
                for lot in lots
            ],
            "trade_history": [
                {
                    "trade_id": t.trade_id or f"trade-{i}",
                    "symbol": t.symbol,
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.qty,
                    "entry_time": t.entry_time or "",
                    "exit_time": t.exit_time or "",
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct * 100, 2),
                    "commission": round(t.commission, 4),
                    "reason": t.reason,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                }
                for i, t in enumerate(self.closed_trades[-50:])
            ],
            "adaptive": {
                "stop_loss_pct": self.adaptive.current_stop_loss_pct,
                "take_profit_pct": self.adaptive.current_take_profit_pct,
                "position_size_pct": self.adaptive.current_position_size_pct,
                "win_rate": self.adaptive.win_rate,
                "total_wins": self.adaptive.total_wins,
                "total_losses": self.adaptive.total_losses,
                "win_streak": self.adaptive.win_streak,
                "loss_streak": self.adaptive.loss_streak,
                "expected_value": round(self.adaptive.expected_value, 2),
                "max_drawdown_pct": self._max_drawdown,
                "total_trades": self.adaptive.total_wins + self.adaptive.total_losses,
            },
            "peak_equity": round(self._peak_equity, 2),
            "max_drawdown": self._max_drawdown,
            "position_value": round(
                sum(
                    abs(lot.qty) * self._current_price
                    if lot.qty > 0
                    else (lot.avg_price + (lot.avg_price - self._current_price)) * abs(lot.qty)
                    for sym, lots in self._open_positions.items()
                    for lot in lots
                ),
                2,
            ),
        }

    def _on_tick(self) -> None:
        """Event-driven simulation step. Triggered on market data updates.

        Complies with Zero Latency Rule (Rule 08) by avoiding asyncio.sleep.
        """
        if not self._running:
            return

        loop_start = time.time()
        try:
            self._tick_count += 1
            self._simulate_price_tick()

            exit_record = self._check_exit_conditions()
            if exit_record:
                self._emit(self._build_snapshot())
            if len(self._price_history) >= self.MIN_HISTORY_FOR_ANALYSIS:
                signal = self._generate_signal()
                if self._managed_positions:
                    dynamic_exit = self._check_dynamic_exit(signal)
                    if dynamic_exit:
                        self._emit(self._build_snapshot())

                if len(self._managed_positions) < self.max_concurrent_positions:
                    if signal:
                        sym = "BTC-USD"
                        existing_lots = self._managed_positions.get(sym, [])
                        if not existing_lots or any(
                            lot.side != signal["action"] for lot in existing_lots
                        ):
                            opened = self._open_managed_position(
                                signal["action"], signal["strength"]
                            )
                            if opened:
                                self._emit(self._build_snapshot())

            if self._tick_count % 5 == 0:
                self._persist_pnl_snapshot()
                self._emit(self._build_snapshot())

            self._last_latency_ms = (time.time() - loop_start) * 1000

            # Rule 08 Compliance: Monitor simulation latency
            if self._last_latency_ms > 100:
                _LOG.warning(f"[PAPER] Latency violation: {self._last_latency_ms:.2f}ms")

                content = f"CRITICAL: Engine latency breach detected. Simulation step took {self._last_latency_ms:.2f}ms."

                # 1. Add to internal thinking history for snapshot
                violation_note = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "thinking": "CRITICAL: Engine latency breach detected.",
                    "explanation": content,
                }
                self._thinking_history.append(violation_note)
                if len(self._thinking_history) > self.THINKING_HISTORY_LIMIT:
                    self._thinking_history.pop(0)

                # 2. Emit ForensicNoteEvent for Auditor/Dashboard capture
                self._publish_to_bus(
                    ForensicNoteEvent(
                        source="PaperTradingEngine",
                        payload=ForensicNotePayload(
                            content=content,
                            note_type="ALERT",
                            session_id=getattr(self, "_session_id", None),
                        ),
                    )
                )

        except Exception as e:
            _LOG.error(f"[PAPER] Simulation tick error: {e}", exc_info=True)

    async def run_continuous(self) -> None:
        """Background loop driving the heartbeat of the simulation.

        Broadcasts MarketEvents to the global EventBus so other containers (Orchestrator, etc.)
        can synchronize to the same price feed.
        """
        from qtrader.core.events import MarketEvent, MarketPayload

        self._running = True
        self._start_time = time.time()
        _LOG.info("[PAPER] Simulation HEARTBEAT started")

        while self._running:
            try:
                # Inject a unique trace ID for each simulation pulse
                trace_id = TraceAuthority.start_trace()

                # 1. Self-drive the price simulation
                self._on_tick()

                # 2. Extract current price and broadcast to system
                price = self._current_price
                if price > 0:
                    event = MarketEvent(
                        source="PaperTradingEngine",
                        payload=MarketPayload(
                            symbol="BTC-USD",
                            price=Decimal(str(price)),
                            data={"price": price},
                            bid=Decimal(str(round(price * 0.9999, 2))),
                            ask=Decimal(str(round(price * 1.0001, 2))),
                        ),
                    )
                    self._last_latency_ms = 0.0  # Internal loop has negligible latency
                    self._publish_to_bus(event)

                # 3. Controlled cadence (default 1s or as configured)
                await asyncio.sleep(self._tick_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOG.error(f"[PAPER] Error in heartbeat loop: {e}")
                await asyncio.sleep(1)

    def stop(self) -> None:
        self._running = False

    def update_base_price(self, price: float, force_current: bool = False) -> None:
        """Update the base (mean-reversion) price and optionally the current price.

        Args:
            price: The new base price (USD)
            force_current: If True, also sets the current simulation price to this value.
        """
        if price <= 0:
            return
        self._base_price = price
        if force_current or not self._running:
            self._current_price = price
        _LOG.info(f"[PAPER] Base price updated to {price:.2f} (force_current={force_current})")

    async def handle_market_event(self, event: Any) -> None:
        """Update simulation state with external real-time market data.

        Accepts MarketEvent from the global EventBus.
        """
        try:
            symbol = event.payload.symbol
            if "BTC-USD" not in symbol:
                return

            data = event.payload.data
            price = float(data.get("price") or 0.0)

            if price <= 0:
                bid = float(event.payload.bid)
                ask = float(event.payload.ask)
                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2.0

            if price > 0:
                old_price = self._current_price
                self._current_price = price
                self._base_price = price
                self._last_external_tick = time.time()

                if (
                    abs(old_price - price) / (old_price or price or 1)
                    > TradeRecord.SIGNIFICANT_PRICE_CHANGE
                ):
                    self._emit(self._build_snapshot())

                # Drive simulation logic on every market tick (Zero Latency Compliance)
                self._on_tick()

        except Exception as e:
            _LOG.error(f"[PAPER] Failed to handle external market data: {e}")

    def clear_history(self) -> None:
        """Clear the price history buffer and reset tick indicators.

        Useful when the base price is updated significantly to avoid
        distorted indicators (e.g. extreme RSI) from stale data.
        """
        self._price_history.clear()
        self._tick_count = 0
        _LOG.info("[PAPER] Price history buffer cleared")

    def reset(self) -> None:
        self._cash = self.starting_capital
        self._current_price = self._base_price
        self._price_history.clear()
        self._open_positions.clear()
        self._managed_positions.clear()
        self.closed_trades.clear()
        self._total_commissions = 0.0
        self._total_gross_pnl = 0.0
        self._peak_equity = self.starting_capital
        self._max_drawdown = 0.0
        self._last_recorded_equity = None
        self.adaptive = AdaptiveConfig(
            base_stop_loss_pct=self.adaptive.base_stop_loss_pct,
            base_take_profit_pct=self.adaptive.base_take_profit_pct,
        )
        _LOG.info("[PAPER] Engine reset")
