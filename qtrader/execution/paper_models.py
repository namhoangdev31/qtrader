from __future__ import annotations
from dataclasses import dataclass


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
    EPSILON_QTY: float = 1e-08
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

    @property
    def commission(self) -> float:
        return self.avg_comm_per_unit * self.qty


@dataclass
class AdaptiveConfig:
    base_stop_loss_pct: float = 0.02
    base_take_profit_pct: float = 0.03
    base_position_size_pct: float = 0.2
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
    max_position_pct: float = 0.5
    min_stop_loss_pct: float = 0.01
    min_take_profit_pct: float = 0.01
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
                base - self.streak_adjust_step * min(self.win_streak, 4), self.min_stop_loss_pct
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
        loss_pnl = self.total_pnl - avg_w * self.total_wins
        avg_l = abs(loss_pnl) / self.total_losses
        return wr * avg_w - (1 - wr) * avg_l
