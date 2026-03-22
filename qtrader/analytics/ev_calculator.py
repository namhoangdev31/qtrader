"""
EVCalculator — computes all core quant metrics from closed trade history.

Metrics implemented (per quant fund standard):
    1. EV (Expectancy)       — mean net profit per trade after fees+slippage
    2. EV %                  — mean net return per trade (normalised by position size)
    3. EV weighted           — total net profit / total capital used (portfolio-aware)
    4. Profit Factor         — gross wins / gross losses
    5. Sharpe Ratio          — mean return / std(return) * sqrt(252) annualised
    6. Max Drawdown          — peak-to-trough drawdown on cumulative PnL curve
    7. Kelly Fraction        — optimal bet sizing fraction
    8. Win/Loss diagnostics  — used for strategy debugging only (NOT as main EV)

Tradability rule-of-thumb (quant threshold):
    EV            > 0
    Trades        > 300
    Profit Factor > 1.3
    Sharpe        > 1.5
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from qtrader.execution.paper_engine import TradeRecord


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class EVReport:
    """Full quant diagnosis report from closed trade history."""
    symbol: str

    # Trade counts
    total_trades: int
    win_count: int
    loss_count: int

    # Core EV (after fees + slippage)
    ev_per_trade: float          # mean NetProfit in base currency
    ev_pct: float                # mean NetProfit / PositionSize  (%)
    ev_weighted: float           # ΣNetProfit / ΣCapitalUsed

    # Cost breakdown
    total_gross_profit: float
    total_fees_slippage: float
    total_net_profit: float

    # Quant metrics
    win_rate: float
    avg_win: float               # avg net profit of winning trades
    avg_loss: float              # avg net loss of losing trades (positive number)
    profit_factor: float         # gross_wins / gross_losses
    sharpe_ratio: float          # annualised Sharpe on trade returns
    sortino_ratio: float         # mean return / downside std * sqrt(annualization)
    calmar_ratio: float          # annualised return / max_drawdown
    payoff_ratio: float          # avg_win / avg_loss
    break_even_win_rate: float   # 1 / (1 + payoff_ratio)
    cost_to_profit_ratio: float  # total_fees / (gross_wins if gross_wins > 0 else 1)
    ev_confidence_interval: float # 95% CI bound: EV ± CI
    max_drawdown: float          # peak-to-trough on cumulative PnL (positive = bad)
    kelly_fraction: float        # optimal bet size fraction

    # Diagnostics
    max_slippage_bps: float
    status: str                  # PASS | WARN | FAIL
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class EVCalculator:
    """
    Compute Expected Value and full quant metrics from a list of TradeRecord.

    Usage::

        calc = EVCalculator(trades=engine.closed_trades, fee_rate=0.0006)
        report = calc.diagnose("BTC-USD")
    """

    # Default Coinbase Advanced Trade taker fee
    DEFAULT_FEE_RATE: float = 0.0004  # 0.04%

    def __init__(
        self,
        trades: list[TradeRecord] | None = None,
        fee_rate: float = DEFAULT_FEE_RATE,
        annualization_factor: float = 252.0 * 78.0,  # Default for 5m standard market (252 days * 78 bars)
    ) -> None:
        self.trades = trades or []
        self.fee_rate = fee_rate
        self.annualization_factor = annualization_factor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_ev_stats(self) -> dict[str, Any]:
        """
        Compute all quant metrics from closed trade history.

        Cost model:
          - gross  = (exit_price - entry_price) × qty  [directional PnL]
          - fees   = (entry_price + exit_price) × qty × fee_rate  [round-trip]
          - net    = gross - fees

        NOTE: TradeRecord.slippage_bps stores abs(exit-entry)/entry*10000.
        This is PRICE MOVEMENT between entry and exit — it is already captured
        in `gross`. Do NOT subtract it again as a cost; doing so would
        double-count the price move and guarantee 0 wins.

        TradeRecord.slippage_bps is used here only as an informational metric
        (max slippage display), NOT as a cost deduction.
        """
        if not self.trades:
            return self._empty_stats()

        net_profits: list[float] = []
        net_returns: list[float] = []
        capital_used: list[float] = []

        total_gross = 0.0
        total_fees = 0.0
        gross_wins = 0.0
        gross_losses = 0.0
        win_count = 0
        loss_count = 0

        for t in self.trades:
            # Gross directional profit
            # Note: t.side is the side of the EXITING trade.
            # SELL/SHORT exit means we were LONG. BUY exit means we were SHORT.
            if t.side.upper() in ("SELL", "SHORT"):
                gross = (t.exit_price - t.entry_price) * t.qty
            else:
                gross = (t.entry_price - t.exit_price) * t.qty

            # Round-trip trading fees only
            fees = (t.entry_price * t.qty * self.fee_rate
                    + t.exit_price * t.qty * self.fee_rate)

            net = gross - fees
            position_size = t.entry_price * t.qty

            net_profits.append(net)
            net_returns.append(net / position_size if position_size > 0 else 0.0)
            capital_used.append(position_size)

            total_gross += gross
            total_fees += fees

            if net > 0:
                gross_wins += net
                win_count += 1
            else:
                gross_losses += abs(net)
                loss_count += 1

        total_net = sum(net_profits)
        total_trades = len(self.trades)
        win_rate = win_count / total_trades
        loss_rate = 1.0 - win_rate

        wins_list = [p for p in net_profits if p > 0]
        losses_list = [abs(p) for p in net_profits if p <= 0]

        avg_win = sum(wins_list) / len(wins_list) if wins_list else 0.0
        avg_loss = sum(losses_list) / len(losses_list) if losses_list else 0.0

        # EV formulas
        ev_per_trade = total_net / total_trades
        ev_pct = sum(net_returns) / total_trades
        total_cap = sum(capital_used)
        ev_weighted = total_net / total_cap if total_cap > 0 else 0.0

        # Profit Factor
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

        # Payoff & Break-even
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else float("inf")
        break_even_win_rate = 1.0 / (1.0 + payoff_ratio) if payoff_ratio != float("inf") else 0.0
        
        # Cost to profit
        cost_to_profit_ratio = total_fees / gross_wins if gross_wins > 0 else float("inf")

        # Sharpe Ratio
        n = len(net_returns)
        mean_r = sum(net_returns) / n if n > 0 else 0.0
        variance = sum((r - mean_r) ** 2 for r in net_returns) / n if n > 0 else 0.0
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        sharpe = (mean_r / std_r) * math.sqrt(self.annualization_factor) if std_r > 0 else 0.0

        # Sortino Ratio
        target = 0.0
        downside_variance = sum(min(r - target, 0.0) ** 2 for r in net_returns) / n if n > 0 else 0.0
        downside_std = math.sqrt(downside_variance)
        sortino = (mean_r / downside_std) * math.sqrt(self.annualization_factor) if downside_std > 0 else 0.0

        # EV Confidence Interval (95%)
        # For EV per trade: mean(net_profits) +- 1.96 * std / sqrt(N)
        net_profits_mean = sum(net_profits) / total_trades
        net_profits_var = sum((p - net_profits_mean)**2 for p in net_profits) / total_trades
        net_profits_std = math.sqrt(net_profits_var)
        ev_confidence_interval = 1.96 * net_profits_std / math.sqrt(total_trades) if total_trades > 0 else 0.0

        # Max Drawdown — use average capital as equity baseline
        # so drawdown is meaningful even when all trades are losses
        avg_capital = total_cap / total_trades if total_trades > 0 else 1.0
        max_drawdown = self._max_drawdown(net_profits, initial_equity=avg_capital)

        # Calmar Ratio
        annualised_return = mean_r * self.annualization_factor
        calmar = (annualised_return / max_drawdown) if max_drawdown > 0 else float("inf")

        # Kelly Fraction
        kelly = 0.0
        if avg_loss > 0 and avg_win > 0:
            kelly = win_rate - (loss_rate / (avg_win / avg_loss))

        max_slip = max((t.slippage_bps for t in self.trades), default=0.0)

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "ev_per_trade": ev_per_trade,
            "ev_pct": ev_pct,
            "ev_weighted": ev_weighted,
            "total_gross_profit": total_gross,
            "total_fees_slippage": total_fees,
            "total_net_profit": total_net,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "payoff_ratio": payoff_ratio,
            "break_even_win_rate": break_even_win_rate,
            "cost_to_profit_ratio": cost_to_profit_ratio,
            "ev_confidence_interval": ev_confidence_interval,
            "max_drawdown": max_drawdown,
            "kelly_fraction": kelly,
            "max_slippage_bps": max_slip,
        }

    def diagnose(
        self,
        target_symbol: str,
        min_trades: int = 300,
        min_profit_factor: float = 1.3,
        min_sharpe: float = 1.5,
    ) -> EVReport:
        """
        Run full quant diagnosis with tradability gate checks.

        Args:
            target_symbol: Symbol label for the report.
            min_trades: Minimum number of trades for statistical significance.
            min_profit_factor: Floor for Profit Factor (default 1.3).
            min_sharpe: Floor for annualised Sharpe Ratio (default 1.5).

        Returns:
            EVReport with status PASS / WARN / FAIL.
        """
        s = self.compute_ev_stats()
        warnings: list[str] = []
        status = "PASS"

        def _fail(msg: str) -> None:
            nonlocal status
            warnings.append(msg)
            status = "FAIL"

        def _warn(msg: str) -> None:
            nonlocal status
            warnings.append(msg)
            if status == "PASS":
                status = "WARN"

        # Gate 1: Trade count
        if s["total_trades"] < min_trades:
            _warn(
                f"Insufficient trade count ({s['total_trades']} / {min_trades}). "
                "Not enough data for statistical confidence. Run more simulations."
            )

        # Gate 2: EV must be positive
        if s["ev_per_trade"] <= 0:
            _fail(
                f"Negative EV ({s['ev_per_trade']:.6f}). "
                "Strategy loses money on average after fees+slippage."
            )

        # Gate 3: Profit Factor
        if s["profit_factor"] < min_profit_factor:
            _fail(
                f"Low Profit Factor ({s['profit_factor']:.2f} < {min_profit_factor}). "
                "Gross wins do not justify gross losses."
            )

        # Gate 4: Sharpe Ratio
        if s["sharpe_ratio"] < min_sharpe:
            _warn(
                f"Low Sharpe Ratio ({s['sharpe_ratio']:.2f} < {min_sharpe}). "
                "Return/risk ratio below institutional standard."
            )

        # Gate 5: Kelly
        if s["kelly_fraction"] <= 0:
            _fail(
                f"Negative Kelly Fraction ({s['kelly_fraction']:.4f}). "
                "Mathematical edge is negative — stop trading this strategy."
            )

        # Gate 6: Slippage warning
        if s["max_slippage_bps"] > 10.0:
            _warn(
                f"High slippage detected ({s['max_slippage_bps']:.1f} bps). "
                "Strategy is hitting illiquid order books."
            )

        return EVReport(
            symbol=target_symbol,
            total_trades=s["total_trades"],
            win_count=s["win_count"],
            loss_count=s["loss_count"],
            ev_per_trade=s["ev_per_trade"],
            ev_pct=s["ev_pct"],
            ev_weighted=s["ev_weighted"],
            total_gross_profit=s["total_gross_profit"],
            total_fees_slippage=s["total_fees_slippage"],
            total_net_profit=s["total_net_profit"],
            win_rate=s["win_rate"],
            avg_win=s["avg_win"],
            avg_loss=s["avg_loss"],
            profit_factor=s["profit_factor"],
            sharpe_ratio=s["sharpe_ratio"],
            sortino_ratio=s["sortino_ratio"],
            calmar_ratio=s["calmar_ratio"],
            payoff_ratio=s["payoff_ratio"],
            break_even_win_rate=s["break_even_win_rate"],
            cost_to_profit_ratio=s["cost_to_profit_ratio"],
            ev_confidence_interval=s["ev_confidence_interval"],
            max_drawdown=s["max_drawdown"],
            kelly_fraction=s["kelly_fraction"],
            max_slippage_bps=s["max_slippage_bps"],
            status=status,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _max_drawdown(self, net_profits: list[float], initial_equity: float = 1.0) -> float:
        """
        Compute max peak-to-trough drawdown on equity curve.

        Uses initial_equity as the starting baseline so that drawdown is
        meaningful even when cumulative PnL never rises above zero
        (all-loss scenario would previously return 0%).

        Returns:
            Positive fraction: 0.15 means 15% peak-to-trough drawdown.
        """
        equity = initial_equity
        peak = initial_equity
        max_dd = 0.0
        for p in net_profits:
            equity += p
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _empty_stats(self) -> dict[str, Any]:
        return {
            "total_trades": 0, "win_count": 0, "loss_count": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "ev_per_trade": 0.0, "ev_pct": 0.0, "ev_weighted": 0.0,
            "total_gross_profit": 0.0, "total_fees_slippage": 0.0, "total_net_profit": 0.0,
            "profit_factor": 0.0, "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0, "calmar_ratio": 0.0,
            "payoff_ratio": 0.0, "break_even_win_rate": 0.0,
            "cost_to_profit_ratio": 0.0, "ev_confidence_interval": 0.0,
            "max_drawdown": 0.0, "kelly_fraction": 0.0, "max_slippage_bps": 0.0,
        }
