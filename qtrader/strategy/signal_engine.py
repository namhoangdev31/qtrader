from __future__ import annotations
import logging
from typing import Any
from qtrader.core.dynamic_config import config_manager
from qtrader.core.session_state import SessionState

logger = logging.getLogger("qtrader.strategy.signal")
try:
    import qtrader_core

    HAS_RUST_CORE = True
    sizing_engine = qtrader_core.SizingEngine()
except ImportError:
    HAS_RUST_CORE = False


class SignalEngine:
    def __init__(self, state: SessionState) -> None:
        self.state = state

    def generate_signal(
        self, symbol: str, ml_result: dict[str, Any], is_exit_check: bool = False
    ) -> dict[str, Any] | None:
        decision = ml_result["decision"]
        if isinstance(decision, dict):
            action_val = decision.get("action", "HOLD")
            action = str(action_val.value if hasattr(action_val, "value") else action_val)
            confidence = float(decision.get("confidence", 0.0))
            reasoning = str(decision.get("reasoning", "No reasoning provided"))
            base_size = float(decision.get("position_size_multiplier", 0.1))
        else:
            action = str(
                decision.action.value if hasattr(decision.action, "value") else decision.action
            )
            confidence = float(decision.confidence)
            reasoning = str(decision.reasoning)
            base_size = float(getattr(decision, "position_size_multiplier", 0.1))
        min_conf = config_manager.get("MIN_CONFIDENCE")
        exit_conf = config_manager.get("EXIT_CONFIDENCE")
        threshold = exit_conf if is_exit_check else min_conf
        if action == "HOLD" or confidence < threshold:
            return None
        kelly_multiplier = self._calculate_kelly_multiplier()
        position_size = base_size * kelly_multiplier
        position_size = min(position_size, config_manager.get("POSITION_SIZE_PCT", 0.5))
        return {
            "symbol": symbol,
            "side": "BUY" if action == "BUY" else "SELL",
            "position_size_multiplier": position_size,
            "confidence": confidence,
            "kelly_multiplier": kelly_multiplier,
            "reasoning": reasoning,
        }

    def _calculate_kelly_multiplier(self) -> float:
        if not self.state.win_history:
            return 1.0
        wins = sum(self.state.win_history)
        total = len(self.state.win_history)
        win_rate = wins / total
        win_loss_ratio = 2.0
        if HAS_RUST_CORE:
            fraction = config_manager.get("KELLY_FRACTION", 0.5)
            kelly_f = sizing_engine.calculate_kelly_fraction(win_rate, win_loss_ratio, fraction)
            return kelly_f * 2.0
        return win_rate

    def check_trend_confirmation(
        self, symbol: str, side: str, market_data_history: list[dict[str, float]]
    ) -> bool:
        lookback = config_manager.get("TREND_LOOKBACK", 10)
        if not market_data_history or len(market_data_history) < lookback:
            return True
        prices = [x["close"] for x in market_data_history[-lookback:]]
        ma_short = sum(prices[-3:]) / 3
        ma_long = sum(prices) / len(prices)
        if side == "BUY":
            return ma_short >= ma_long
        return ma_short <= ma_long

    def check_exit_triggers(
        self,
        symbol: str,
        current_price: float,
        positions_lots: list[Any],
        sl_pct: float,
        tp_pct: float,
    ) -> dict[str, Any] | None:
        if not positions_lots:
            return None
        for lot in positions_lots:
            if isinstance(lot, dict):
                avg_entry = float(lot.get("avg_price", 0.0))
                side = lot.get("side", "BUY")
                trade_id = lot.get("trade_id", "unknown")
            else:
                avg_entry = float(getattr(lot, "avg_price", 0.0))
                side = getattr(lot, "side", "BUY")
                trade_id = getattr(lot, "trade_id", "unknown")
            pnl_pct = (current_price - avg_entry) / avg_entry if avg_entry > 0 else 0
            if side == "BUY":
                if pnl_pct <= -sl_pct:
                    return {
                        "symbol": symbol,
                        "side": "SELL",
                        "reason": "STOP_LOSS",
                        "lot_id": trade_id,
                    }
                if pnl_pct >= tp_pct:
                    return {
                        "symbol": symbol,
                        "side": "SELL",
                        "reason": "TAKE_PROFIT",
                        "lot_id": trade_id,
                    }
            elif side == "SELL":
                if pnl_pct >= sl_pct:
                    return {
                        "symbol": symbol,
                        "side": "BUY",
                        "reason": "STOP_LOSS",
                        "lot_id": trade_id,
                    }
                if pnl_pct <= -tp_pct:
                    return {
                        "symbol": symbol,
                        "side": "BUY",
                        "reason": "TAKE_PROFIT",
                        "lot_id": trade_id,
                    }
        return None
