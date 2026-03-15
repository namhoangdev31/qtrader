from dataclasses import dataclass
from typing import Any

from qtrader.output.execution.paper_engine import TradeRecord


@dataclass
class DiagnosisReport:
    symbol: str
    total_trades: int
    win_rate: float
    ev_per_trade: float
    avg_win: float
    avg_loss: float
    max_slippage_bps: float
    kelly_fraction: float
    status: str
    warnings: list[str]


class EVCalculator:
    """
    Computes Expected Value (EV), Win Rate, and Kelly Criterion from simulated trade history.
    Used for safe 'Go-Live' validation.
    """

    def __init__(self, trades: list[TradeRecord] | None = None) -> None:
        self.trades = trades or []

    def compute_ev_stats(self) -> dict[str, Any]:
        if not self.trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "ev": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "kelly_fraction": 0.0,
            }

        wins = [t.pnl_pct for t in self.trades if t.pnl > 0]
        losses = [abs(t.pnl_pct) for t in self.trades if t.pnl <= 0]

        total = len(self.trades)
        win_rate = len(wins) / total
        loss_rate = 1.0 - win_rate

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        # EV = (Win% * Avg_Win) - (Loss% * Avg_Loss)
        ev = (win_rate * avg_win) - (loss_rate * avg_loss)

        # Kelly Fraction = W - [(1 - W) / (Avg_Win / Avg_Loss)]   (if Avg_Loss > 0)
        kelly = 0.0
        if avg_loss > 0 and avg_win > 0:
            kelly = win_rate - (loss_rate / (avg_win / avg_loss))

        return {
            "total_trades": total,
            "win_rate": win_rate,
            "ev": ev,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_slippage": max((t.slippage_bps for t in self.trades), default=0.0),
            "kelly_fraction": kelly,
        }

    def diagnose(self, target_symbol: str) -> DiagnosisReport:
        stats = self.compute_ev_stats()
        warnings = []
        status = "PASS"

        if stats["total_trades"] < 30:
            warnings.append(f"Insufficient trade count ({stats['total_trades']}). Need at least 30 for statistical significance.")
            status = "FAIL"

        if stats["ev"] <= 0:
            warnings.append(f"Negative Expected Value ({stats['ev']:.4f}). Strategy is guaranteed to lose money over time.")
            status = "FAIL"

        if stats["win_rate"] < 0.52:
            warnings.append(f"Low Win Rate ({stats['win_rate']:.1%}). Must win >52% to safely beat exchange fees.")
            if status == "PASS":
                status = "WARN"

        if stats["max_slippage"] > 10.0:
            warnings.append(f"High Max Slippage detected ({stats['max_slippage']:.1f} bps). Strategy is hitting illiquid order books.")
            if status == "PASS":
                status = "WARN"

        if stats["kelly_fraction"] <= 0:
            warnings.append(f"Negative Kelly Fraction ({stats['kelly_fraction']:.4f}). Stop trading this strategy immediately.")
            status = "FAIL"

        return DiagnosisReport(
            symbol=target_symbol,
            total_trades=stats["total_trades"],
            win_rate=stats["win_rate"],
            ev_per_trade=stats["ev"],
            avg_win=stats["avg_win"],
            avg_loss=stats["avg_loss"],
            max_slippage_bps=stats["max_slippage"],
            kelly_fraction=stats["kelly_fraction"],
            status=status,
            warnings=warnings,
        )
