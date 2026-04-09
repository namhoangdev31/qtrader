from __future__ import annotations

import logging
import math
import time
from typing import Any

_LOG = logging.getLogger("qtrader.analytics.reporting")


class InvestorReportingEngine:
    def __init__(self) -> None:
        self._total_reports_produced: int = 0
        self._historical_peak_equity: float = 0.0

    def generate_investor_analytics(
        self,
        nav_history: list[float],
        period_label: str = "MONTHLY",
        annual_risk_free_rate: float = 0.02,
    ) -> dict[str, Any]:
        generation_start = time.time()
        min_required_points = 2
        if len(nav_history) < min_required_points:
            return {
                "status": "INSUFFICIENT_DATA",
                "details": "Institutional reporting requires minimum 2 data points.",
            }
        returns: list[float] = []
        peak_observed = nav_history[0]
        max_drawdown_observed = 0.0
        for i in range(1, len(nav_history)):
            prev_nav = nav_history[i - 1]
            curr_nav = nav_history[i]
            r_t = (curr_nav - prev_nav) / prev_nav if prev_nav > 0 else 0.0
            returns.append(r_t)
            peak_observed = max(peak_observed, curr_nav)
            drawdown_divergence = (
                (peak_observed - curr_nav) / peak_observed if peak_observed > 0 else 0.0
            )
            max_drawdown_observed = max(max_drawdown_observed, drawdown_divergence)
        num_sessions = len(returns)
        trading_sessions_pa = 252
        annualization_scalar = math.sqrt(trading_sessions_pa)
        avg_daily_return = sum(returns) / num_sessions
        variance = sum((r - avg_daily_return) ** 2 for r in returns) / num_sessions
        daily_volatility = math.sqrt(variance)
        annualized_return = avg_daily_return * trading_sessions_pa
        annualized_volatility = daily_volatility * annualization_scalar
        excess_return = annualized_return - annual_risk_free_rate
        sharpe_ratio = excess_return / annualized_volatility if annualized_volatility > 0 else 0.0
        self._total_reports_produced += 1
        self._historical_peak_equity = max(self._historical_peak_equity, peak_observed)
        _LOG.info(
            f"[REPORTING] ANALYTICS_GENERATED | Sharpe: {sharpe_ratio:.2f} | MaxDD: {max_drawdown_observed:.2%} | Reports: {self._total_reports_produced}"
        )
        artifact = {
            "status": "ANALYTICS_FINALIZED",
            "metadata": {
                "period": period_label,
                "dataset_size": len(nav_history),
                "timestamp": time.time(),
            },
            "performance": {
                "total_cumulative_return_pct": round(
                    (nav_history[-1] / nav_history[0] - 1) * 100, 4
                ),
                "annualized_return_pct": round(annualized_return * 100, 4),
                "daily_mean_return_basis": round(avg_daily_return, 6),
            },
            "risk_metrics": {
                "sharpe_ratio_basis": round(sharpe_ratio, 4),
                "annualized_volatility_pct": round(annualized_volatility * 100, 4),
                "max_drawdown_captured_pct": round(max_drawdown_observed * 100, 4),
            },
            "forensics": {
                "peak_equity_historical": round(self._historical_peak_equity, 4),
                "generation_latency_ms": round((time.time() - generation_start) * 1000, 4),
            },
        }
        return artifact

    def get_reporting_telemetry(self) -> dict[str, Any]:
        return {
            "status": "METRICS_GOVERNANCE",
            "total_reports_to_date": self._total_reports_produced,
            "peak_equity_historical": round(self._historical_peak_equity, 4),
        }
