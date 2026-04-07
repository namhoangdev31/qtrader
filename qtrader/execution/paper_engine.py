"""Paper Trading Engine with continuous simulation, SL/TP, and adaptive strategy.

Executes simulated orders against real Coinbase market data.
Tracks P&L, computes realistic slippage via Kyle's Lambda,
and supports continuous autonomous trading with adaptive parameters.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from qtrader.core.events import (
    FillEvent,
    FillPayload,
    OrderEvent,
)

_LOG = logging.getLogger("qtrader.paper")


@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    slippage_bps: float
    venue: str
    DEFAULT_SL_PCT: float = 0.02
    DEFAULT_TP_PCT: float = 0.05
    EPSILON_QTY: float = 1e-8
    MIN_HISTORY_FOR_ANALYSIS: int = 20
    SIGNIFICANT_PRICE_CHANGE: float = 0.0001
    reason: str = "SIGNAL"
    stop_loss: float = 0.0
    take_profit: float = 0.0
    entry_time: str = ""
    exit_time: str = ""
    commission: float = 0.0
    trade_id: str = ""


@dataclass
class OpenPosition:
    symbol: str
    side: str
    qty: float
    avg_price: float
    avg_comm_per_unit: float
    stop_loss: float
    take_profit: float
    entry_time: str
    position_id: str = ""


@dataclass
class AdaptiveConfig:
    base_stop_loss_pct: float = 0.02
    base_take_profit_pct: float = 0.03
    base_position_size_pct: float = 0.20
    max_position_usd: float = 5000.0

    win_streak: int = 0
    loss_streak: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_pnl: float = 0.0

    streak_adjust_step: float = 0.005
    max_sl_adjustment: float = 0.03
    max_tp_adjustment: float = 0.05
    min_position_pct: float = 0.05
    max_position_pct: float = 0.50
    min_stop_loss_pct: float = 0.01
    min_take_profit_pct: float = 0.01

    # Streak thresholds
    STREAK_LOSS_CRITICAL: int = 3
    STREAK_WIN_STABLE: int = 2
    STREAK_MAX_ADJUST_WINDOWS: int = 6
    STREAK_WIN_REWARD: int = 3

    @property
    def current_stop_loss_pct(self) -> float:
        base = self.base_stop_loss_pct
        if self.loss_streak >= self.STREAK_LOSS_CRITICAL:
            adj = self.streak_adjust_step * min(self.loss_streak, self.STREAK_MAX_ADJUST_WINDOWS)
            return min(base + adj, base + self.max_sl_adjustment)
        if self.win_streak >= self.STREAK_WIN_STABLE:
            return max(
                base - self.streak_adjust_step * min(self.win_streak, 4),
                self.min_stop_loss_pct,
            )
        return base

    @property
    def current_take_profit_pct(self) -> float:
        base = self.base_take_profit_pct
        if self.loss_streak >= self.STREAK_LOSS_CRITICAL:
            adj = self.streak_adjust_step * min(self.loss_streak, self.STREAK_MAX_ADJUST_WINDOWS)
            return max(base - adj, base - self.max_tp_adjustment)
        if self.win_streak >= self.STREAK_WIN_STABLE:
            return min(
                base + self.streak_adjust_step * min(self.win_streak, 4),
                base + self.max_tp_adjustment,
            )
        # Ensure TP doesn't drop below floor
        return max(base, self.min_take_profit_pct)

    @property
    def current_position_size_pct(self) -> float:
        base = self.base_position_size_pct
        if self.loss_streak >= self.STREAK_WIN_STABLE:
            adj = self.streak_adjust_step * min(self.loss_streak, self.STREAK_MAX_ADJUST_WINDOWS)
            return max(base - adj, self.min_position_pct)
        if self.win_streak >= self.STREAK_WIN_REWARD:
            return min(
                base + self.streak_adjust_step * min(self.win_streak, 4), self.max_position_pct
            )
        return base

    def record_win(self, pnl: float) -> None:
        self.win_streak += 1
        self.loss_streak = 0
        self.total_wins += 1
        self.total_pnl += pnl

    def record_loss(self, pnl: float) -> None:
        self.loss_streak += 1
        self.win_streak = 0
        self.total_losses += 1
        self.total_pnl += pnl

    @property
    def win_rate(self) -> float:
        total = self.total_wins + self.total_losses
        return self.total_wins / total if total > 0 else 0.0

    @property
    def expected_value(self) -> float:
        wr = self.win_rate
        if wr in {0, 1} or self.total_losses == 0:
            return 0.0
        avg_w = self.total_pnl / max(self.total_wins, 1) if self.total_wins > 0 else 0
        loss_pnl = self.total_pnl - (avg_w * self.total_wins)
        avg_l = abs(loss_pnl) / self.total_losses
        return wr * avg_w - (1 - wr) * avg_l


class PaperTradingEngine:
    """Paper trading with continuous simulation, SL/TP, and adaptive strategy."""

    def __init__(
        self,
        starting_capital: float = 1000.0,
        fee_rate: float = 0.0,  # No longer used as a flat taker fee
        performance_fee: float = 0.15,
        max_concurrent_positions: int = 10,
        max_trades_history: int = 100_000,
        sl_pct: float = 0.02,
        tp_pct: float = 0.03,
        tick_interval: float = 0.2,
        base_price: float = 50000.0,
    ) -> None:
        self.TAKER_FEE: float = 0.0060  # 0.60%
        self.MAKER_FEE: float = 0.0040  # 0.40%
        
        # Fidelity Layer Configuration
        self.LATENCY_MIN_MS: int = 50
        self.LATENCY_MAX_MS: int = 300
        self.ERROR_PROBABILITY: float = 0.01  # 1% chance of execution failure
        self.SLIPPAGE_VOL_MULT: float = 0.5   # Multiplier for volatility-based slippage
        
        self.starting_capital = starting_capital
        self.performance_fee = performance_fee
        self.max_concurrent_positions = max_concurrent_positions
        self.closed_trades: list[TradeRecord] = []
        self._max_trades_history = max_trades_history

        # Simulation Constants
        self.PRICE_HISTORY_LIMIT = 5000
        self.PRICE_HISTORY_PRUNE = 2000
        self.MIN_HISTORY_FOR_ANALYSIS = 20
        self.RSI_PERIOD = 14
        self.RSI_BULL_GATE = 45.0
        self.RSI_BEAR_GATE = 55.0
        self.RSI_OVERSOLD = 45.0  # Aggressive: enter buy sooner
        self.RSI_OVERBOUGHT = 55.0 # Aggressive: enter sell sooner
        self.REVERSAL_THRESHOLD = 0.35
        self.MIN_TRADE_NOTIONAL = 10.0
        self.EPSILON_QTY = 1e-8
        self.THINKING_HISTORY_LIMIT = 100

        self._open_positions: dict[str, list[OpenPosition]] = {}
        self._managed_positions: dict[str, list[OpenPosition]] = {}

        self.adaptive = AdaptiveConfig(
            base_stop_loss_pct=sl_pct,
            base_take_profit_pct=tp_pct,
        )

        self._cash = starting_capital
        self._total_commissions = 0.0
        self._total_gross_pnl = 0.0
        self._peak_equity = starting_capital
        self._max_drawdown = 0.0
        self._current_price = base_price
        self._base_price = base_price
        self._price_history: list[float] = []
        self._volatility = 0.002
        self._running = False
        self._tick_interval = tick_interval
        self._last_external_tick = 0.0
        self._last_thinking = "Awaiting first analysis..."
        self._last_explanation = "Simulation engine is initializing market data buffer..."
        self._thinking_history: list[dict[str, Any]] = []
        self._last_trace: dict[str, Any] = {
            "module_traces": {
                "AlphaEngine": {"status": "INITIALIZING"},
                "RiskEngine": {"status": "INITIALIZING"},
                "RiskGuard": {"status": "INITIALIZING"},
                "Portfolio": {"status": "INITIALIZING"},
                "Reconciliation": {"status": "AWAITING"},
                "Strategy": {"status": "AWAITING"}
            }
        }

        self.EXTERNAL_TICK_TIMEOUT = 2.0

        self._on_update: Callable[[dict[str, Any]], None] | None = None

    def set_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._on_update = handler

    def _emit(self, data: dict[str, Any]) -> None:
        if self._on_update:
            try:
                self._on_update(data)
            except Exception as e:
                _LOG.error(f"[PAPER] Update handler error: {e}")

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def equity(self) -> float:
        market_value = 0.0
        # CORRECTED: Flatten lots
        for lots in self._open_positions.values():
            for lot in lots:
                qty, avg_price, _ = lot
                if qty > 0:
                    market_value += qty * self._current_price
                elif qty < 0:
                    notional = abs(qty) * avg_price
                    pnl = (avg_price - self._current_price) * abs(qty)
                    market_value += notional + pnl
        return self._cash + market_value

    @property
    def realized_pnl(self) -> float:
        market_value = 0.0
        notional_value = 0.0
        # CORRECTED: Flatten lots
        for lots in self._open_positions.values():
            for lot in lots:
                qty, avg_price, _ = lot
                notional_value += abs(qty) * avg_price
                if qty > 0:
                    market_value += qty * self._current_price
                else:
                    pnl = (avg_price - self._current_price) * abs(qty)
                    market_value += (abs(qty) * avg_price) + pnl
        
        unrealized_gross = market_value - notional_value
        total_pnl = self.equity - self.starting_capital
        return total_pnl - unrealized_gross

    @property
    def total_commissions(self) -> float:
        return self._total_commissions

    def _simulate_price_tick(self) -> float:
        if time.time() - self._last_external_tick < self.EXTERNAL_TICK_TIMEOUT:
            self._price_history.append(self._current_price)
            if len(self._price_history) > self.PRICE_HISTORY_LIMIT:
                self._price_history = self._price_history[-self.PRICE_HISTORY_PRUNE:]
            return self._current_price

        self._price_history.append(self._current_price)
        if len(self._price_history) > self.PRICE_HISTORY_LIMIT:
            self._price_history = self._price_history[-self.PRICE_HISTORY_PRUNE:]
        
        # Capture Ingestion Trace
        self._last_trace["ingestion"] = {
            "price": self._current_price,
            "volatility": self._volatility,
            "spread_bps": 2.0,  
            "is_live": time.time() - self._last_external_tick < self.EXTERNAL_TICK_TIMEOUT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": random.randint(self.LATENCY_MIN_MS, self.LATENCY_MAX_MS) if self._running else 0
        }
        
        # Simulate execution latency if running
        if self._running:
            # We don't sleep here to avoid blocking the loop, but we use this value in traces
            pass

        return self._current_price

    def _generate_signal(self) -> dict[str, Any] | None:
        if len(self._price_history) < self.MIN_HISTORY_FOR_ANALYSIS:
            return None
        
        # We now allow signal generation while in position to support DYNAMIC_EXIT

        recent = self._price_history[-20:]
        sma_short = sum(recent[-5:]) / 5
        sma_long = sum(recent[-10:]) / 10

        rsi = 50.0
        if len(recent) >= self.RSI_PERIOD:
            gains, losses = [], []
            for i in range(1, min(self.RSI_PERIOD + 1, len(recent))):
                diff = recent[i] - recent[i - 1]
                gains.append(diff if diff > 0 else 0)
                losses.append(abs(diff) if diff < 0 else 0)
            avg_g = sum(gains) / len(gains) if gains else 0
            avg_l = sum(losses) / len(losses) if losses else 1
            rs = avg_g / max(avg_l, 0.0001)
            rsi = 100 - 100 / (1 + rs)

        if sma_short > sma_long * 1.0001 and rsi < self.RSI_BULL_GATE:
            self._last_thinking = (
                f"SMA Bullish Cross ({sma_short:.2f} > {sma_long:.2f}) | "
                f"RSI Oversold ({rsi:.1f})"
            )
            self._last_explanation = (
                f"The system detected a bullish SMA crossover with RSI at {rsi:.1f}. "
                "Executing adaptive entry with confirmed momentum."
            )
            res = {"action": "BUY", "strength": 0.5 + random.SystemRandom().random() * 0.3}
        elif sma_short < sma_long * 0.9999 and rsi > self.RSI_BEAR_GATE:
            self._last_thinking = (
                f"SMA Bearish Cross ({sma_short:.2f} < {sma_long:.2f}) | "
                f"RSI Overbought ({rsi:.1f})"
            )
            self._last_explanation = (
                f"Bearish SMA crossover detected. RSI is at {rsi:.1f}, "
                "suggesting overbought conditions. Risk protocols suggest "
                "a short position to capture the expected mean reversion."
            )
            res = {"action": "SELL", "strength": 0.5 + random.SystemRandom().random() * 0.3}
        else:
            # Update thinking even on HOLD
            res = None
            if rsi < self.RSI_OVERSOLD:
                self._last_thinking = f"Extreme RSI Oversold ({rsi:.1f}) - Monitoring base"
                self._last_explanation = (
                    "RSI is extremely low. Waiting for bottom confirmation before entry."
                )
            elif rsi > self.RSI_OVERBOUGHT:
                self._last_thinking = f"Extreme RSI Overbought ({rsi:.1f}) - Monitoring peak"
                self._last_explanation = (
                    "RSI is extremely high. Monitoring for exhaustion "
                    "before considering shorts."
                )
            else:
                self._last_thinking = (
                    f"Market Neutral | RSI: {rsi:.1f} | "
                    f"SMA Delta: {abs(sma_short - sma_long):.2f}"
                )
                self._last_explanation = (
                    "No strong directional conviction. Maintaining HOLD status "
                    "to preserve capital."
                )
 
        # Capture Alpha Trace
        self._last_trace["alpha"] = {
            "model_name": "AtomicTrio_Sim",
            "action": res["action"] if res else "HOLD",
            "confidence": res["strength"] if res else 0.5,
            "indicators": {
                "rsi": rsi,
                "sma_short": sma_short,
                "sma_long": sma_long,
                "sma_delta": sma_short - sma_long
            },
            "reasoning": self._last_explanation
        }
        
        self._last_trace["module_traces"]["AlphaEngine"] = self._last_trace["alpha"]
        self._last_trace["module_traces"]["Execution"] = {
            "name": "PaperEngine_Sim",
            "last_slippage_bps": round(self._last_slippage * 10000, 2) if hasattr(self, "_last_slippage") else 0.0,
            "status": "DANGER" if (getattr(self, "_last_slippage", 0.0) > 0.01) else "OK",
            "is_anomaly": getattr(self, "_last_slippage", 0.0) > 0.01  # Slippage > 100bps
        }
        self._last_trace["module_traces"]["RiskGuard"] = {
            "name": "DynamicGuardrail_Sim",
            "sl_pct": self.adaptive.current_stop_loss_pct,
            "tp_pct": self.adaptive.current_take_profit_pct,
            "status": "ACTIVE"
        }
        
        self._last_trace["module_traces"]["RiskEngine"] = {
            "is_halted": False,
            "reason": "OK",
            "dd_limit": self.adaptive.max_sl_adjustment,
            "status": "HEALTHY"
        }
        total_notional = 0.0
        for lots in self._open_positions.values():
            for lot_data in lots:
                total_notional += lot_data[0] * lot_data[1]

        self._last_trace["module_traces"]["Portfolio"] = {
            "equity": float(self._cash + total_notional),
            "cash": float(self._cash),
            "allocation_pct": float(self.adaptive.current_position_size_pct),
            "status": "HEALTHY"
        }
        self._last_trace["module_traces"]["Reconciliation"] = {
            "mismatch_count": 0,
            "status": "OK"
        }
        self._last_trace["module_traces"]["Strategy"] = {
            "win_streak": self.adaptive.win_streak,
            "loss_streak": self.adaptive.loss_streak,
            "win_rate": round(self.adaptive.win_rate, 4),
            "status": "ACTIVE"
        }
        self._thinking_history.append({
            "timestamp": time.time(),
            "thinking": self._last_thinking,
            "explanation": self._last_explanation
        })
        if len(self._thinking_history) > self.THINKING_HISTORY_LIMIT:
            self._thinking_history = self._thinking_history[-self.THINKING_HISTORY_LIMIT:]

        return res
    def _open_managed_position(self, side: str, strength: float) -> OpenPosition | None:
        """Execute an adaptive entry with institutional fidelity simulation."""
        pos_pct = self.adaptive.current_position_size_pct * strength
        notional = self._cash * pos_pct

        if notional < self.MIN_TRADE_NOTIONAL:
            return None

        sym = "BTC-USD"
        
        if random.random() < self.ERROR_PROBABILITY:
            _LOG.warning(f"[PAPER] Execution Error Injection: Simulated Timeout for {side} {sym}")
            return None

        slippage_pct = (self._volatility * self.SLIPPAGE_VOL_MULT) * (1 + random.random())
        price = self._current_price * (1 + (slippage_pct if side == "BUY" else -slippage_pct))
        
        qty = notional / price

        sl_pct = self.adaptive.current_stop_loss_pct
        tp_pct = self.adaptive.current_take_profit_pct
 
        # Calculate stops based on fill price
        sl = price * (1 - sl_pct) if side == "BUY" else price * (1 + sl_pct)
        tp = price * (1 + tp_pct) if side == "BUY" else price * (1 - tp_pct)

        # Institutional Fee Structure (Coinbase Taker 0.60%)
        entry_fee = notional * self.TAKER_FEE
        self._cash -= (notional + entry_fee)
        self._total_commissions += entry_fee
        commission_per_unit = entry_fee / qty
        
        sign = 1 if side == "BUY" else -1
        
        if sym not in self._open_positions:
            self._open_positions[sym] = []
        # Store as (signed_qty, avg_price, comm_per_unit) 
        self._open_positions[sym].append((qty * sign, price, commission_per_unit))

        pos = OpenPosition(
            symbol=sym,
            side=side,
            qty=qty,
            avg_price=price,
            avg_comm_per_unit=commission_per_unit,
            stop_loss=sl,
            take_profit=tp,
            entry_time=datetime.now(timezone.utc).isoformat(),
            position_id=str(uuid.uuid4())
        )
        
        if sym not in self._managed_positions:
            self._managed_positions[sym] = []
        self._managed_positions[sym].append(pos)
        
        _LOG.info(
            f"[PAPER] OPEN {side} {sym} qty={qty:.6f} @ {price:.2f} | "
            f"SL={sl:.2f} TP={tp:.2f} | Notional=${notional:.2f}"
        )
        return pos

    def _check_exit_conditions(self) -> TradeRecord | None:
        for sym, positions in list(self._managed_positions.items()):
            for pos in list(positions):
                price = self._current_price
                reason = None
                if pos.side == "BUY":
                    if price <= pos.stop_loss:
                        reason = "STOP_LOSS"
                    elif price >= pos.take_profit:
                        reason = "TAKE_PROFIT"
                elif price >= pos.stop_loss:
                    reason = "STOP_LOSS"
                elif price <= pos.take_profit:
                    reason = "TAKE_PROFIT"
                
                if reason:
                    return self._close_managed_position(sym, reason, price)
        return None

    def _check_dynamic_exit(self, signal: dict[str, Any] | None) -> TradeRecord | None:
        """Check if current signals warrant an early tactical exit."""
        if not signal or not self._managed_positions:
            return None
        
        for sym, positions in list(self._managed_positions.items()):
            for pos in list(positions):
                action = signal.get("action")
                strength = signal.get("strength", 0.0)
                
                # Reversal Detection: Exit if signal contradicts current position
                should_exit = False
                if (pos.side == "BUY" and action == "SELL" and 
                    strength >= self.REVERSAL_THRESHOLD):
                    should_exit = True
                elif (pos.side == "SELL" and action == "BUY" and 
                      strength >= self.REVERSAL_THRESHOLD):
                    should_exit = True
                    
                if should_exit:
                    _LOG.info(
                        f"[PAPER] DYNAMIC_EXIT triggered for {sym} | "
                        f"Signal={action} strength={strength:.2f}"
                    )
                    return self._close_managed_position(sym, "DYNAMIC_EXIT", self._current_price)
        
        return None

    def _close_managed_position(self, symbol: str, reason: str, exit_price: float) -> TradeRecord:
        if not self._managed_positions.get(symbol):
            raise ValueError(f"No managed position to close for {symbol}")
            
        pos = self._managed_positions[symbol].pop(0)
        
        if pos.side == "BUY":
            # LONG: Gross = (Exit - Entry) * Qty
            gross_pnl = (exit_price - pos.avg_price) * pos.qty
        else:
            # SHORT: Gross = (Entry - Exit) * Qty
            gross_pnl = (pos.avg_price - exit_price) * pos.qty

        # 1. Execution Fee (Coinbase Taker 0.60%)
        execution_fee = (exit_price * pos.qty) * self.TAKER_FEE
        
        # 2. Performance Fee (HWM): 15% of positive gross PnL ONLY if new peak equity
        exit_perf_fee = 0.0
        
        # Calculate what current equity WOULD be without performance fee
        notional_entry = pos.avg_price * pos.qty
        equity_before_perf = self._cash + (notional_entry + gross_pnl) - execution_fee
        
        if gross_pnl > 0 and equity_before_perf > self._peak_equity:
            new_profit_above_peak = equity_before_perf - self._peak_equity
            exit_perf_fee = min(gross_pnl * self.performance_fee, new_profit_above_peak * self.performance_fee)
        
        total_comm = pos.commission + execution_fee + exit_perf_fee
        net_pnl = gross_pnl - (pos.commission + execution_fee + exit_perf_fee)
        
        # Net Return % = Net PnL / Entry Notional
        net_pnl_pct = net_pnl / (pos.avg_price * pos.qty) if pos.avg_price > 0 else 0

        # SETTLEMENT: Return Notional + Gross PnL - Fees
        self._cash += (notional_entry + gross_pnl) - execution_fee - exit_perf_fee
        
        self._total_commissions += (execution_fee + exit_perf_fee)
        self._total_gross_pnl += gross_pnl
        
        if not self._managed_positions[symbol]:
            self._managed_positions.pop(symbol)
            self._open_positions.pop(symbol, None)

        if net_pnl > 0:
            self.adaptive.record_win(net_pnl)
        else:
            self.adaptive.record_loss(net_pnl)

        # Update peak equity after transaction
        curr_eq = self.equity
        self._peak_equity = max(self._peak_equity, curr_eq)

        # Fidelity Update: Dynamic Exit Slippage
        exit_slippage_pct = (self._volatility * self.SLIPPAGE_VOL_MULT) * (1 + random.random())
        adjusted_exit_price = exit_price * (1 - (exit_slippage_pct if pos.side == "BUY" else -exit_slippage_pct))
        
        ref_mid = self._current_price
        slippage_bps = (abs(adjusted_exit_price - exit_price) / exit_price * 10000) if exit_price > 0 else 0

        trade = TradeRecord(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.avg_price,
            exit_price=adjusted_exit_price,
            qty=pos.qty,
            pnl=net_pnl,
            pnl_pct=net_pnl_pct,
            slippage_bps=slippage_bps,
            venue="SIMULATED",
            reason=reason,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            entry_time=pos.entry_time,
            exit_time=datetime.now(timezone.utc).isoformat(),
            commission=execution_fee + exit_perf_fee,
            trade_id=str(uuid.uuid4()),
        )
        self.closed_trades.append(trade)
        if len(self.closed_trades) > self._max_trades_history:
            self.closed_trades = self.closed_trades[-self._max_trades_history // 2 :]

        # Update drawdown
        peak = self.equity
        self._peak_equity = max(self._peak_equity, peak)
        dd = (self._peak_equity - self.equity) / self._peak_equity if self._peak_equity > 0 else 0
        self._max_drawdown = max(self._max_drawdown, dd)

        _LOG.info(
            f"[PAPER] CLOSE {reason} {symbol} {pos.side} | "
            f"Entry={pos.avg_price:.2f} Exit={exit_price:.2f} | "
            f"PnL=${net_pnl:.2f} ({net_pnl_pct:.2f}%) | WR={self.adaptive.win_rate:.1%}"
        )

        # Capture Execution Trace
        self._last_trace["execution"] = {
            "order_id": trade.trade_id,
            "fill_price": exit_price,
            "slippage_bps": slippage_bps,
            "fee_usd": exit_comm,
            "status": "FILLED"
        }

        return trade

    def _kyle_lambda(self, order_qty: float, top_depth: float) -> float:
        if top_depth <= 0:
            return 0.0005
        ratio = order_qty / top_depth
        impact = 0.00002 + (0.0001 * ratio)
        return min(impact, 0.0010)

    def simulate_fill(self, order: OrderEvent, market_state: dict[str, Any]) -> FillEvent:
        bid = float(market_state.get("bid", 0.0))
        ask = float(market_state.get("ask", 0.0))
        top_depth = float(market_state.get("top_depth", 0.0))
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0

        if ask <= 0 or bid <= 0:
            _LOG.warning(f"Invalid market state for {order.symbol}: bid={bid}, ask={ask}")
            price = float(order.price) if order.price else 0.0
            if price <= 0:
                raise ValueError(f"No valid price available to fill {order.symbol}")
        else:
            slippage = self._kyle_lambda(float(order.quantity), top_depth)
            if order.side.upper() == "BUY":
                price = ask * (1 + slippage)
            else:
                price = bid * (1 - slippage)
 
        # Flat taker fee removed in favor of performance fee on exit
        commission = 0.0

        fill = FillEvent(
            source="PaperTradingEngine",
            payload=FillPayload(
                order_id=order.order_id or str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=Decimal(str(price)),
                commission=Decimal(str(commission)),
            ),
        )

        self._record_trade(fill, market_state.get("venue", "SIMULATED_COINBASE"), mid)
        return fill

    def _record_trade(self, fill: FillEvent, venue: str, mid_price: float) -> None:
        sym = fill.payload.symbol
        side = fill.payload.side.upper()
        qty = float(fill.payload.quantity)
        price = float(fill.payload.price)
        comm = float(fill.payload.commission)
        comm_per_unit = comm / qty if qty > 0 else 0.0
        ref_mid = mid_price if mid_price > 0 else price

        curr_qty, curr_price, curr_comm_per_unit = self._open_positions.get(sym, (0.0, 0.0, 0.0))

        if sym not in self._open_positions or not isinstance(self._open_positions[sym], list):
            self._open_positions[sym] = []
            
        if not self._open_positions[sym]:
            sign = 1 if side == "BUY" else -1
            self._open_positions[sym].append((qty * sign, price, comm_per_unit))
        elif (curr_qty > 0 and side == "BUY") or (curr_qty < 0 and side == "SELL"):
            sign = 1 if side == "BUY" else -1
            total_qty = abs(curr_qty) + qty
            avg_price = ((abs(curr_qty) * curr_price) + (qty * price)) / total_qty
            avg_comm = ((abs(curr_qty) * curr_comm_per_unit) + comm) / total_qty
            self._open_positions[sym] = (total_qty * sign, avg_price, avg_comm)
        else:
            closing_qty = min(abs(curr_qty), qty)
            if curr_qty > 0:
                gross_pnl = (price - curr_price) * closing_qty
                pnl_pct = (price - curr_price) / curr_price if curr_price > 0 else 0
            else:
                gross_pnl = (curr_price - price) * closing_qty
                pnl_pct = (curr_price - price) / curr_price if curr_price > 0 else 0

            exit_comm_share = (comm / qty) * closing_qty
            entry_comm_share = curr_comm_per_unit * closing_qty
            net_pnl = gross_pnl - entry_comm_share - exit_comm_share
            slippage_bps = (abs(price - ref_mid) / ref_mid) * 10000.0 if ref_mid > 0 else 0

            record = TradeRecord(
                symbol=sym,
                side=side,
                entry_price=curr_price,
                exit_price=price,
                qty=closing_qty,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                slippage_bps=slippage_bps,
                venue=venue,
                commission=comm,
            )
            self.closed_trades.append(record)
            if len(self.closed_trades) > self._max_trades_history:
                self.closed_trades = self.closed_trades[-self._max_trades_history // 2 :]

            rem_qty = abs(curr_qty) - closing_qty
            sign = 1 if curr_qty > 0 else -1
            if rem_qty < self.EPSILON_QTY:
                self._open_positions.pop(sym, None)
            else:
                self._open_positions[sym] = [(rem_qty * sign, curr_price, curr_comm_per_unit)]

            if qty > closing_qty:
                flipped_qty = qty - closing_qty
                flipped_sign = 1 if side == "BUY" else -1
                self._open_positions[sym] = [(flipped_qty * flipped_sign, price, comm_per_unit)]

    def _build_snapshot(self) -> dict[str, Any]:
        eq = self.equity
        realized = self.realized_pnl
        return {
            "type": "simulation_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "open_positions": [
                {
                    "symbol": sym,
                    "side": "BUY" if lot[0] > 0 else "SELL",
                    "quantity": abs(lot[0]),
                    "entry_price": lot[1],
                    "current_price": self._current_price,
                    "unrealized_pnl": round(
                        (self._current_price - lot[1]) * lot[0]
                        if lot[0] > 0
                        else (lot[1] - self._current_price) * abs(lot[0]),
                        2,
                    ),
                    "unrealized_pnl_pct": round(
                        ((self._current_price - lot[1]) / lot[1] * 100)
                        if lot[1] > 0
                        else 0,
                        2,
                    ),
                    "stop_loss": 0.0,
                    "take_profit": 0.0,
                    "entry_time": "",
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
                    abs(qty) * self._current_price
                    if qty > 0
                    else (avg_price + (avg_price - self._current_price)) * abs(qty)
                    for sym, (qty, avg_price, _) in self._open_positions.items()
                ),
                2,
            ),
        }

    async def run_continuous(self) -> None:
        """Main continuous simulation loop."""
        self._running = True
        _LOG.info(f"[PAPER] Starting continuous simulation | capital=${self.starting_capital}")

        tick = 0
        while self._running:
            try:
                tick += 1
                self._simulate_price_tick()

                # Check static exits (SL/TP)
                exit_record = self._check_exit_conditions()
                if exit_record:
                    self._emit(self._build_snapshot())

                # Continuous Market Analysis
                if len(self._price_history) >= self.MIN_HISTORY_FOR_ANALYSIS:
                    signal = self._generate_signal()
                    
                    # 1. If in position, check for tactical AI exit
                    if self._managed_positions:
                        dynamic_exit = self._check_dynamic_exit(signal)
                        if dynamic_exit:
                            self._emit(self._build_snapshot())
                    
                    # Multi-order logic: Open new positions if limits allow
                    if len(self._managed_positions) < self.max_concurrent_positions:
                        if signal:
                            # Avoid doubling down on the same side 
                            # if it contributes too much to concentration
                            sym = "BTC-USD"
                            existing = self._managed_positions.get(sym)
                            if not existing or existing.side != signal["action"]:
                                opened = self._open_managed_position(
                                    signal["action"], 
                                    signal["strength"]
                                )
                                if opened:
                                    self._emit(self._build_snapshot())

                if tick % 5 == 0:
                    self._emit(self._build_snapshot())

                await asyncio.sleep(self._tick_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOG.error(f"[PAPER] Simulation error: {e}", exc_info=True)
                await asyncio.sleep(0.5)

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
            # Detect symbol and price from MarketPayload or ticker data
            symbol = event.payload.symbol
            if "BTC-USD" not in symbol:
                return

            # Extract price from payload (pre-calculated) or raw data (ticker)
            # In qtrader.trading_system._on_market_data_update, 'price' is added to data
            data = event.payload.data
            price = float(data.get("price") or 0.0)

            if price <= 0:
                # Fallback to mid-match if ticker price is missing
                bid = float(event.payload.bid)
                ask = float(event.payload.ask)
                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2.0

            if price > 0:
                old_price = self._current_price
                self._current_price = price
                self._base_price = price
                self._last_external_tick = time.time()

                # If price changed significantly, emit a snapshot update immediately
                if abs(old_price - price) / (old_price or price or 1) > TradeRecord.SIGNIFICANT_PRICE_CHANGE:
                    self._emit(self._build_snapshot())

        except Exception as e:
            _LOG.error(f"[PAPER] Failed to handle external market data: {e}")

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
        self.adaptive = AdaptiveConfig(
            base_stop_loss_pct=self.adaptive.base_stop_loss_pct,
            base_take_profit_pct=self.adaptive.base_take_profit_pct,
        )
        _LOG.info("[PAPER] Engine reset")
