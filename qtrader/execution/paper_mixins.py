from __future__ import annotations
import asyncio
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from qtrader.core.events import FillEvent, FillPayload, OrderEvent, SignalEvent, SignalPayload
from qtrader.execution.paper_models import OpenPosition, TradeRecord

_LOG = logging.getLogger("qtrader.paper")


class SignalMixin:
    def _simulate_price_tick(self) -> float:
        if time.time() - self._last_external_tick < self.EXTERNAL_TICK_TIMEOUT:
            self._price_history.append(self._current_price)
            if len(self._price_history) > self.PRICE_HISTORY_LIMIT:
                self._price_history = self._price_history[-self.PRICE_HISTORY_PRUNE :]
            return self._current_price
        drift = self.MEAN_REVERSION_STRENGTH * (self._base_price - self._current_price)
        noise = random.gauss(0, self._volatility * self._current_price)
        self._current_price = max(self._current_price + drift + noise, self._base_price * 0.8)
        self._price_history.append(self._current_price)
        if len(self._price_history) > self.PRICE_HISTORY_LIMIT:
            self._price_history = self._price_history[-self.PRICE_HISTORY_PRUNE :]
        self._last_trace["ingestion"] = {
            "price": self._current_price,
            "volatility": self._volatility,
            "spread_bps": 2.0,
            "is_live": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": random.randint(self.LATENCY_MIN_MS, self.LATENCY_MAX_MS)
            if self._running
            else 0,
        }
        self._last_trace["module_traces"]["ingestion"] = self._last_trace["ingestion"]
        return self._current_price

    def _generate_signal(self) -> dict[str, Any] | None:
        if len(self._price_history) < self.MIN_HISTORY_FOR_ANALYSIS:
            return None
        recent = self._price_history[-self.SMA_LONG_WINDOW * 2 :]
        if len(recent) < self.SMA_LONG_WINDOW:
            return None
        sma_short = sum(recent[-self.SMA_SHORT_WINDOW :]) / self.SMA_SHORT_WINDOW
        sma_long = sum(recent[-self.SMA_LONG_WINDOW :]) / self.SMA_LONG_WINDOW
        rsi = 50.0
        if len(recent) >= self.RSI_PERIOD:
            (gains, losses) = ([], [])
            for i in range(1, min(self.RSI_PERIOD + 1, len(recent))):
                diff = recent[i] - recent[i - 1]
                gains.append(diff if diff > 0 else 0)
                losses.append(abs(diff) if diff < 0 else 0)
            avg_g = sum(gains) / len(gains) if gains else 0
            avg_l = sum(losses) / len(losses) if losses else 0
            if avg_g == 0 and avg_l == 0:
                rsi = 50.0
            elif avg_l == 0:
                rsi = 100.0
            else:
                rs = avg_g / avg_l
                rsi = 100 - 100 / (1 + rs)
        rsi = max(0.0, min(100.0, rsi))
        if sma_short > sma_long * (1 + self.CROSSOVER_THRESHOLD) and rsi < self.RSI_BULL_GATE:
            self._last_thinking = (
                f"SMA Bullish Cross ({sma_short:.2f} > {sma_long:.2f}) | RSI Oversold ({rsi:.1f})"
            )
            self._last_explanation = f"The system detected a bullish SMA crossover with RSI at {rsi:.1f}. Executing adaptive entry with confirmed momentum."
            res = {"action": "BUY", "strength": 0.5 + random.SystemRandom().random() * 0.3}
        elif sma_short < sma_long * (1 - self.CROSSOVER_THRESHOLD) and rsi > self.RSI_BEAR_GATE:
            self._last_thinking = (
                f"SMA Bearish Cross ({sma_short:.2f} < {sma_long:.2f}) | RSI Overbought ({rsi:.1f})"
            )
            self._last_explanation = f"Bearish SMA crossover detected. RSI is at {rsi:.1f}, suggesting overbought conditions. Risk protocols suggest a short position to capture the expected mean reversion."
            res = {"action": "SELL", "strength": 0.5 + random.SystemRandom().random() * 0.3}
        else:
            res = None
            if rsi < self.RSI_OVERSOLD:
                self._last_thinking = f"Extreme RSI Oversold ({rsi:.1f}) - Monitoring base"
                self._last_explanation = (
                    "RSI is extremely low. Waiting for bottom confirmation before entry."
                )
            elif rsi > self.RSI_OVERBOUGHT:
                self._last_thinking = f"Extreme RSI Overbought ({rsi:.1f}) - Monitoring peak"
                self._last_explanation = (
                    "RSI is extremely high. Monitoring for exhaustion before considering shorts."
                )
            else:
                self._last_thinking = (
                    f"Market Neutral | RSI: {rsi:.1f} | SMA Delta: {abs(sma_short - sma_long):.2f}"
                )
                self._last_explanation = (
                    "No strong directional conviction. Maintaining HOLD status to preserve capital."
                )
        self._last_trace["alpha"] = {
            "model_name": "AtomicTrio_Sim",
            "action": res["action"] if res else "HOLD",
            "confidence": res["strength"] if res else 0.5,
            "indicators": {
                "rsi": rsi,
                "sma_short": sma_short,
                "sma_long": sma_long,
                "sma_delta": sma_short - sma_long,
            },
            "reasoning": self._last_explanation,
        }
        self._last_trace["module_traces"]["AlphaEngine"] = self._last_trace["alpha"]
        self._last_trace["module_traces"]["alpha"] = self._last_trace["alpha"]
        anomaly_threshold = self.ANOMALY_THRESHOLD
        last_slip = getattr(self, "_last_slippage", 0.0)
        self._last_trace["module_traces"]["execution"] = {
            "name": "PaperEngine_Sim",
            "last_slippage_bps": round(last_slip * 10000, 2),
            "slippage_bps": round(last_slip * 10000, 2),
            "status": "DANGER" if last_slip > anomaly_threshold else "OK",
            "is_anomaly": last_slip > anomaly_threshold,
        }
        self._last_trace["module_traces"]["RiskGuard"] = {
            "name": "DynamicGuardrail_Sim",
            "sl_pct": self.adaptive.current_stop_loss_pct,
            "tp_pct": self.adaptive.current_take_profit_pct,
            "status": "ACTIVE",
        }
        self._last_trace["module_traces"]["risk"] = {
            "initial_stop_loss": self.adaptive.current_stop_loss_pct * self._current_price,
            "sl_pct": self.adaptive.current_stop_loss_pct,
            "status": "ACTIVE",
        }
        self._last_trace["module_traces"]["RiskEngine"] = {
            "is_halted": False,
            "reason": "OK",
            "dd_limit": self.adaptive.max_sl_adjustment,
            "status": "HEALTHY",
        }
        total_notional = 0.0
        for lots in self._open_positions.values():
            for lot in lots:
                total_notional += lot.qty * lot.avg_price
        self._last_trace["module_traces"]["Portfolio"] = {
            "equity": float(self._cash + total_notional),
            "cash": float(self._cash),
            "allocation_pct": float(self.adaptive.current_position_size_pct),
            "status": "HEALTHY",
        }
        self._last_trace["module_traces"]["Reconciliation"] = {"mismatch_count": 0, "status": "OK"}
        self._last_trace["module_traces"]["Strategy"] = {
            "win_streak": self.adaptive.win_streak,
            "loss_streak": self.adaptive.loss_streak,
            "win_rate": round(self.adaptive.win_rate, 4),
            "status": "ACTIVE",
        }
        self._thinking_history.append(
            {
                "timestamp": time.time(),
                "action": res["action"] if res else "HOLD",
                "thinking": self._last_thinking,
                "explanation": self._last_explanation,
            }
        )
        if len(self._thinking_history) > self.THINKING_HISTORY_LIMIT:
            self._thinking_history = self._thinking_history[-self.THINKING_HISTORY_LIMIT :]
        self._persist_thinking_log(
            action=res["action"] if res else "HOLD", confidence=res["strength"] if res else 0.5
        )
        return res


class PositionMixin:
    def _open_managed_position(self, side: str, strength: float) -> OpenPosition | None:
        pos_pct = self.adaptive.current_position_size_pct * strength
        notional = self._cash * pos_pct
        if notional < self.MIN_TRADE_NOTIONAL:
            return None
        sym = "BTC-USD"
        if random.random() < self.ERROR_PROBABILITY:
            _LOG.warning(f"[PAPER] Execution Error Injection: Simulated Timeout for {side} {sym}")
            return None
        slippage_pct = self._volatility * self.SLIPPAGE_VOL_MULT * (1 + random.random())
        price = self._current_price * (1 + (slippage_pct if side == "BUY" else -slippage_pct))
        qty = notional / price
        sl_pct = self.adaptive.current_stop_loss_pct
        tp_pct = self.adaptive.current_take_profit_pct
        sl = price * (1 - sl_pct) if side == "BUY" else price * (1 + sl_pct)
        tp = price * (1 + tp_pct) if side == "BUY" else price * (1 - tp_pct)
        entry_fee = notional * self.TAKER_FEE
        self._cash -= notional + entry_fee
        self._total_commissions += entry_fee
        commission_per_unit = entry_fee / qty
        if sym not in self._open_positions:
            self._open_positions[sym] = []
        pos = OpenPosition(
            symbol=sym,
            side=side,
            qty=qty,
            avg_price=price,
            avg_comm_per_unit=commission_per_unit,
            stop_loss=sl,
            take_profit=tp,
            entry_time=datetime.now(timezone.utc).isoformat(),
            position_id=str(uuid.uuid4()),
        )
        self._open_positions[sym].append(pos)
        if sym not in self._managed_positions:
            self._managed_positions[sym] = []
        self._managed_positions[sym].append(pos)
        _LOG.info(
            f"[PAPER] OPEN {side} {sym} qty={qty:.6f} @ {price:.2f} | SL={sl:.2f} TP={tp:.2f} | Notional=${notional:.2f}"
        )
        self._publish_to_bus(
            SignalEvent(
                source="PaperTradingEngine",
                payload=SignalPayload(
                    symbol=sym,
                    signal_type=side,
                    strength=Decimal(str(round(strength, 4))),
                    confidence=Decimal(str(round(min(strength, 1.0), 4))),
                    metadata={
                        "notional": notional,
                        "price": price,
                        "thinking": getattr(self, "_last_thinking", ""),
                        "explanation": getattr(self, "_last_explanation", ""),
                    },
                ),
            )
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
        if not signal or not self._managed_positions:
            return None
        for sym, positions in list(self._managed_positions.items()):
            for pos in list(positions):
                action = signal.get("action")
                strength = signal.get("strength", 0.0)
                should_exit = False
                if pos.side == "BUY" and action == "SELL" and (strength >= self.REVERSAL_THRESHOLD):
                    should_exit = True
                elif (
                    pos.side == "SELL" and action == "BUY" and (strength >= self.REVERSAL_THRESHOLD)
                ):
                    should_exit = True
                if should_exit:
                    _LOG.info(
                        f"[PAPER] DYNAMIC_EXIT triggered for {sym} | Signal={action} strength={strength:.2f}"
                    )
                    return self._close_managed_position(sym, "DYNAMIC_EXIT", self._current_price)
        return None

    def _close_managed_position(self, symbol: str, reason: str, exit_price: float) -> TradeRecord:
        if not self._managed_positions.get(symbol):
            raise ValueError(f"No managed position to close for {symbol}")
        pos = self._managed_positions[symbol].pop(0)
        if pos.side == "BUY":
            gross_pnl = (exit_price - pos.avg_price) * pos.qty
        else:
            gross_pnl = (pos.avg_price - exit_price) * pos.qty
        execution_fee = exit_price * pos.qty * self.TAKER_FEE
        exit_perf_fee = 0.0
        notional_entry = pos.avg_price * pos.qty
        equity_before_perf = self._cash + (notional_entry + gross_pnl) - execution_fee
        if gross_pnl > 0 and equity_before_perf > self._peak_equity:
            new_profit_above_peak = equity_before_perf - self._peak_equity
            exit_perf_fee = min(
                gross_pnl * self.performance_fee, new_profit_above_peak * self.performance_fee
            )
        net_pnl = gross_pnl - (pos.commission + execution_fee + exit_perf_fee)
        net_pnl_pct = net_pnl / (pos.avg_price * pos.qty) if pos.avg_price > 0 else 0
        self._cash += notional_entry + gross_pnl - execution_fee - exit_perf_fee
        self._total_commissions += execution_fee + exit_perf_fee
        self._total_gross_pnl += gross_pnl
        if not self._managed_positions[symbol]:
            self._managed_positions.pop(symbol)
        if symbol in self._open_positions:
            self._open_positions[symbol] = [
                l for l in self._open_positions[symbol] if l.position_id != pos.position_id
            ]
            if not self._open_positions[symbol]:
                self._open_positions.pop(symbol)
        if net_pnl > 0:
            self.adaptive.record_win(net_pnl)
        else:
            self.adaptive.record_loss(net_pnl)
        curr_eq = self.equity
        self._peak_equity = max(self._peak_equity, curr_eq)
        exit_slippage_pct = self._volatility * self.SLIPPAGE_VOL_MULT * (1 + random.random())
        adjusted_exit_price = exit_price * (
            1 - (exit_slippage_pct if pos.side == "BUY" else -exit_slippage_pct)
        )
        slippage_bps = (
            abs(adjusted_exit_price - exit_price) / exit_price * 10000 if exit_price > 0 else 0
        )
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
        peak = self.equity
        self._peak_equity = max(self._peak_equity, peak)
        dd = (self._peak_equity - self.equity) / self._peak_equity if self._peak_equity > 0 else 0
        self._max_drawdown = max(self._max_drawdown, dd)
        _LOG.info(
            f"[PAPER] CLOSE {reason} {symbol} {pos.side} | Entry={pos.avg_price:.2f} Exit={exit_price:.2f} | PnL=${net_pnl:.2f} ({net_pnl_pct:.2f}%) | WR={self.adaptive.win_rate:.1%}"
        )
        self._last_trace["module_traces"]["execution"] = {
            "order_id": trade.trade_id,
            "fill_price": exit_price,
            "slippage_bps": slippage_bps,
            "fee_usd": execution_fee + exit_perf_fee,
            "status": "FILLED",
        }
        self._persist_fill(
            order_id=trade.trade_id,
            symbol=symbol,
            side=pos.side,
            quantity=pos.qty,
            price=exit_price,
            commission=execution_fee + exit_perf_fee,
        )
        self._persist_pnl_snapshot()
        self._publish_to_bus(
            FillEvent(
                source="PaperTradingEngine",
                payload=FillPayload(
                    order_id=trade.trade_id or str(uuid.uuid4()),
                    symbol=symbol,
                    side=pos.side,
                    quantity=Decimal(str(round(pos.qty, 8))),
                    price=Decimal(str(round(exit_price, 2))),
                    commission=Decimal(str(round(execution_fee + exit_perf_fee, 4))),
                    session_id=getattr(self, "_session_id", None),
                    metadata={"reason": reason, "pnl": round(net_pnl, 4)},
                ),
            )
        )
        return trade


class FillMixin:
    def _kyle_lambda(self, order_qty: float, top_depth: float) -> float:
        if top_depth <= 0:
            return 0.0005
        ratio = order_qty / top_depth
        impact = 2e-05 + 0.0001 * ratio
        return min(impact, 0.001)

    def simulate_fill(self, order: OrderEvent, market_state: dict[str, Any]) -> FillEvent:
        bid = float(market_state.get("bid", 0.0))
        ask = float(market_state.get("ask", 0.0))
        top_depth = float(market_state.get("top_depth", 0.0))
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
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
        lots = self._open_positions.get(sym, [])
        if lots and isinstance(lots, list):
            curr_qty = sum((lot.qty for lot in lots))
            curr_price = lots[0].avg_price
            curr_comm_per_unit = lots[0].avg_comm_per_unit
        else:
            (curr_qty, curr_price, curr_comm_per_unit) = (0.0, 0.0, 0.0)
        if sym not in self._open_positions or not isinstance(self._open_positions[sym], list):
            self._open_positions[sym] = []
        if not self._open_positions[sym]:
            self._open_positions[sym].append(
                OpenPosition(
                    symbol=sym,
                    side=side,
                    qty=qty,
                    avg_price=price,
                    avg_comm_per_unit=comm_per_unit,
                    stop_loss=price * (1 - self.adaptive.current_stop_loss_pct)
                    if side == "BUY"
                    else price * (1 + self.adaptive.current_stop_loss_pct),
                    take_profit=price * (1 + self.adaptive.current_take_profit_pct)
                    if side == "BUY"
                    else price * (1 - self.adaptive.current_take_profit_pct),
                    entry_time=datetime.now(timezone.utc).isoformat(),
                    position_id=str(uuid.uuid4()),
                )
            )
        elif (
            self._open_positions[sym][0].qty > 0
            and side == "BUY"
            or (self._open_positions[sym][0].qty < 0 and side == "SELL")
        ):
            lot = self._open_positions[sym][0]
            old_qty = lot.qty
            new_qty = old_qty + qty * (1 if side == "BUY" else -1)
            lot.avg_price = (abs(old_qty) * lot.avg_price + qty * price) / abs(new_qty)
            lot.avg_comm_per_unit = (abs(old_qty) * lot.avg_comm_per_unit + comm) / abs(new_qty)
            lot.qty = new_qty
        else:
            closing_qty = min(abs(curr_qty), qty)
            if curr_qty > 0:
                gross_pnl = (price - curr_price) * closing_qty
                pnl_pct = (price - curr_price) / curr_price if curr_price > 0 else 0
            else:
                gross_pnl = (curr_price - price) * closing_qty
                pnl_pct = (curr_price - price) / curr_price if curr_price > 0 else 0
            exit_comm_share = comm / qty * closing_qty
            entry_comm_share = curr_comm_per_unit * closing_qty
            net_pnl = gross_pnl - entry_comm_share - exit_comm_share
            slippage_bps = abs(price - ref_mid) / ref_mid * 10000.0 if ref_mid > 0 else 0
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
                self._open_positions[sym].pop(0)
                if not self._open_positions[sym]:
                    self._open_positions.pop(sym, None)
            else:
                self._open_positions[sym][0].qty = rem_qty * sign
            if qty > closing_qty:
                flipped_qty = qty - closing_qty
                self._open_positions[sym] = [
                    OpenPosition(
                        symbol=sym,
                        side=side,
                        qty=flipped_qty,
                        avg_price=price,
                        avg_comm_per_unit=comm_per_unit,
                        stop_loss=price * (1 - self.adaptive.current_stop_loss_pct)
                        if side == "BUY"
                        else price * (1 + self.adaptive.current_stop_loss_pct),
                        take_profit=price * (1 + self.adaptive.current_take_profit_pct)
                        if side == "BUY"
                        else price * (1 - self.adaptive.current_take_profit_pct),
                        entry_time=datetime.now(timezone.utc).isoformat(),
                        position_id=str(uuid.uuid4()),
                    )
                ]


class PersistenceMixin:
    def set_db_writer(self, db_writer: Any, session_id: str) -> None:
        self._db_writer = db_writer
        self._session_id = session_id
        _LOG.info(f"[PAPER] DB persistence bridge activated (session={session_id})")

    def set_event_bus(self, event_bus: Any) -> None:
        self._event_bus = event_bus
        _LOG.info("[PAPER] EventBus bridge activated — ForensicAuditor will receive sim events")

    def _publish_to_bus(self, event: Any) -> None:
        bus = getattr(self, "_event_bus", None)
        if bus is None:
            return
        try:
            asyncio.create_task(bus.publish(event))
        except Exception as e:
            _LOG.warning(f"[PAPER] Failed to publish event to bus: {e}")

    def _persist_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        commission: float,
    ) -> None:
        if not self._db_writer or not self._session_id:
            return
        try:
            asyncio.create_task(
                self._db_writer.write_fill(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    quantity=Decimal(str(quantity)),
                    price=Decimal(str(price)),
                    commission=Decimal(str(commission)),
                    source="PaperTradingEngine",
                    session_id=self._session_id,
                )
            )
        except Exception as e:
            _LOG.error(f"[PAPER/DB] Failed to persist fill: {e}")

    def _persist_thinking_log(self, action: str, confidence: float) -> None:
        if not self._db_writer or not self._session_id:
            return
        try:
            asyncio.create_task(
                self._db_writer.write_thinking_log(
                    symbol="BTC-USD",
                    action=action,
                    confidence=confidence,
                    thinking=self._last_thinking,
                    explanation=self._last_explanation,
                    session_id=self._session_id,
                )
            )
        except Exception as e:
            _LOG.error(f"[PAPER/DB] Failed to persist thinking log: {e}")

    def _persist_pnl_snapshot(self) -> None:
        if not self._db_writer or not self._session_id:
            return
        current_eq = round(self.equity, 4)
        if self._last_recorded_equity is not None and current_eq == self._last_recorded_equity:
            return
        self._last_recorded_equity = current_eq
        try:
            asyncio.create_task(
                self._db_writer.write_pnl_snapshot(
                    total_equity=Decimal(str(current_eq)),
                    cash=Decimal(str(round(self._cash, 4))),
                    realized_pnl=Decimal(str(round(self.realized_pnl, 4))),
                    unrealized_pnl=Decimal(str(round(current_eq - self._cash, 4))),
                    total_commission=Decimal(str(round(self._total_commissions, 4))),
                    session_id=self._session_id,
                )
            )
        except Exception as e:
            _LOG.error(f"[PAPER/DB] Failed to persist PnL snapshot: {e}")
