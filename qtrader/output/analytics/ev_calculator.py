"""
EVCalculator — computes all core quant metrics from VectorBT Portfolio object.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
import pandas as pd
import vectorbt as vbt


@dataclass
class EVReport:
    """Full quant diagnosis report from VectorBT Portfolio."""
    symbol: str

    total_trades: int
    win_count: int
    loss_count: int

    ev_per_trade: float          
    ev_pct: float                
    ev_weighted: float           

    total_gross_profit: float
    total_fees_slippage: float
    total_net_profit: float

    win_rate: float
    avg_win: float               
    avg_loss: float              
    profit_factor: float         
    sharpe_ratio: float          
    sortino_ratio: float         
    calmar_ratio: float          
    payoff_ratio: float          
    break_even_win_rate: float   
    cost_to_profit_ratio: float  
    ev_confidence_interval: float 
    max_drawdown: float          
    kelly_fraction: float        

    max_slippage_bps: float
    status: str                  
    warnings: list[str] = field(default_factory=list)


class EVCalculator:
    """
    Compute Expected Value and full quant metrics from a VectorBT Portfolio.
    """

    def __init__(
        self,
        portfolio: vbt.Portfolio | None = None,
        annualization_factor: float = 252.0 * 78.0,
    ) -> None:
        self.portfolio = portfolio
        self.annualization_factor = annualization_factor

    def compute_ev_stats(self) -> dict[str, Any]:
        if self.portfolio is None or len(self.portfolio.trades) == 0:
            return self._empty_stats()
            
        pf = self.portfolio
        trades = pf.trades
        
        # Trade counts
        total_trades = trades.count()
        win_count = trades.winning.count()
        loss_count = trades.losing.count()
        win_rate = win_count / total_trades if total_trades > 0 else 0
        loss_rate = 1.0 - win_rate
        
        # PnL
        total_net = pf.total_profit()
        # VBT tracks fees internally. We can approximate total fees if needed, but 
        # for now we focus on the core net metrics.
        total_fees = pf.fees.sum() if hasattr(pf, 'fees') and pf.fees is not None else 0.0
        
        # In VBT, total_profit is net. Gross is roughly total_profit + total_fees
        total_gross = total_net + total_fees
        
        # Averages
        avg_win = trades.winning.pnl.mean() if win_count > 0 else 0.0
        avg_loss = abs(trades.losing.pnl.mean()) if loss_count > 0 else 0.0
        
        gross_wins = trades.winning.pnl.sum()
        gross_losses = abs(trades.losing.pnl.sum())
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")
        
        ev_per_trade = trades.pnl.mean()
        ev_pct = trades.returns.mean() * 100
        ev_weighted = total_net / pf.init_cash
        
        # Ratios
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else float("inf")
        break_even_win_rate = 1.0 / (1.0 + payoff_ratio) if payoff_ratio != float("inf") else 0.0
        cost_to_profit_ratio = total_fees / gross_wins if gross_wins > 0 else float("inf")
        
        # Retrieve VBT computed stats
        # VectorBT handles annualization via its frequency parameter natively, 
        # but we can also manually calculate it to enforce 5m constraints.
        stats = pf.stats()
        
        sharpe = stats.get('Sharpe Ratio', 0.0)
        if pd.isna(sharpe): sharpe = 0.0
            
        sortino = stats.get('Sortino Ratio', 0.0)
        if pd.isna(sortino): sortino = 0.0
        
        max_drawdown = abs(stats.get('Max Drawdown [%]', 0.0)) / 100.0
        if pd.isna(max_drawdown): max_drawdown = 0.0
            
        calmar = stats.get('Calmar Ratio', 0.0)
        if pd.isna(calmar): calmar = 0.0
        
        # EV Confidence Interval (95%)
        net_profits_std = trades.pnl.std()
        ev_confidence_interval = 1.96 * net_profits_std / math.sqrt(total_trades) if total_trades > 0 and not pd.isna(net_profits_std) else 0.0
        
        # Kelly Fraction
        kelly = 0.0
        if avg_loss > 0 and avg_win > 0:
            kelly = win_rate - (loss_rate / (avg_win / avg_loss))

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
            "max_slippage_bps": 0.0, # Handled by VBT slippage param
        }

    def diagnose(
        self,
        target_symbol: str,
        min_trades: int = 300,
        min_profit_factor: float = 1.3,
        min_sharpe: float = 1.5,
    ) -> EVReport:
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

        if s["total_trades"] < min_trades:
            _warn(f"Insufficient trade count ({s['total_trades']} / {min_trades}).")

        if s["ev_per_trade"] <= 0:
            _fail(f"Negative EV ({s['ev_per_trade']:.6f}).")

        if s["profit_factor"] < min_profit_factor:
            _warn(f"Low Profit Factor ({s['profit_factor']:.2f} < {min_profit_factor}).")

        if s["sharpe_ratio"] < min_sharpe:
            _warn(f"Low Sharpe Ratio ({s['sharpe_ratio']:.2f} < {min_sharpe}).")

        # Create report
        report_data = {k: v for k, v in s.items()}
        report_data["symbol"] = target_symbol
        report_data["status"] = status
        report_data["warnings"] = warnings
        return EVReport(**report_data)

    def _empty_stats(self) -> dict[str, Any]:
        return {
            "total_trades": 0, "win_count": 0, "loss_count": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "ev_per_trade": 0.0, "ev_pct": 0.0,
            "ev_weighted": 0.0, "total_gross_profit": 0.0, "total_fees_slippage": 0.0,
            "total_net_profit": 0.0, "profit_factor": 0.0, "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0, "calmar_ratio": 0.0, "payoff_ratio": 0.0,
            "break_even_win_rate": 0.0, "cost_to_profit_ratio": 0.0,
            "ev_confidence_interval": 0.0, "max_drawdown": 0.0, "kelly_fraction": 0.0,
            "max_slippage_bps": 0.0,
        }
