from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.meta.shadow_enforcer")


@dataclass(slots=True, frozen=True)
class ShadowMetrics:
    """
    Industrial Container for Real-Time Shadow Metrics.
    """

    strategy_id: str
    pnl: float  # Cumulative PnL during shadow period
    slippage: float  # Realized slippage in basis points (bps)
    fill_rate: float  # Percentage of orders fully executed (0.0 to 1.0)
    pnl_deviation: float  # Volatility of PnL vs. baseline expectations


class ShadowEnforcer:
    """
    Principal Shadow Testing Engine.

    Objective: Deterministically validate alpha signals in live market conditions.
    Compares strategy performance against institutional baselines (TWAP/VWAP)
    and enforces strict execution quality gates (slippage/fills).
    """

    def __init__(
        self,
        min_duration_days: int = 7,
        max_slippage_bps: float = 10.0,
        min_fill_rate: float = 0.95,
        max_pnl_deviation: float = 0.5,
    ) -> None:
        """
        Initialize the enforcer constraints.

        Args:
            min_duration_days: Minimum required consecutive days of shadow data.
            max_slippage_bps: Maximum allowable execution slippage.
            min_fill_rate: Minimum required order fill rate.
            max_pnl_deviation: Maximum allowed PnL variance vs. baseline.
        """
        self._min_days = min_duration_days
        self._max_slippage = max_slippage_bps
        self._min_fill = min_fill_rate
        self._max_dev = max_pnl_deviation

        # Telemetry
        self._stats = {"evaluated": 0, "passed": 0, "avg_delta": 0.0}

    def evaluate(
        self,
        strategy_metrics: ShadowMetrics,
        baseline_metrics: ShadowMetrics,
        duration_days: int,
    ) -> dict[str, Any]:
        """
        Determine if the strategy is authorized for promotion to LIVE.

        Logic:
        1. Enforce 7-day minimum duration.
        2. Compare Δ PnL vs. Baseline (TWAP).
        3. Enforce Slippage & Fill Rate thresholds.

        Args:
            strategy_metrics: Realized metrics from the strategy.
            baseline_metrics: Metrics from the institutional benchmark.
            duration_days: Total consecutive days in shadow state.

        Returns:
            dict containing promotion decision (PASS/FAIL) and audit reasoning.
        """
        self._stats["evaluated"] += 1

        # 1. Mandatory Duration Gate
        if duration_days < self._min_days:
            _LOG.info(
                f"FAIL | {strategy_metrics.strategy_id} | "
                f"Duration {duration_days} < Min {self._min_days}"
            )
            return {
                "status": "SHADOW_TEST",
                "result": "FAIL",
                "reason": "INSUFFICIENT_DURATION",
                "delta": 0.0,
            }

        # 2. Performance Comparison (Alpha vs. Baseline)
        delta = strategy_metrics.pnl - baseline_metrics.pnl

        rejections: list[str] = []
        if delta < 0:
            rejections.append(f"NEGATIVE_ALPHA:{delta:.2f}")

        # 3. Execution Quality Gates
        if strategy_metrics.slippage > self._max_slippage:
            rejections.append(f"HIGH_SLIPPAGE:{strategy_metrics.slippage:.2f}bps")

        if strategy_metrics.fill_rate < self._min_fill:
            rejections.append(f"LOW_FILL_RATE:{strategy_metrics.fill_rate:.2%}")

        if rejections:
            _LOG.info(f"FAIL | {strategy_metrics.strategy_id} | Gates: {', '.join(rejections)}")
            self._update_avg_delta(delta)
            return {
                "status": "SHADOW_TEST",
                "result": "FAIL",
                "reason": "; ".join(rejections),
                "delta": round(delta, 2),
            }

        # 4. Success Terminal State
        self._stats["passed"] += 1
        self._update_avg_delta(delta)

        _LOG.info(f"PASS | {strategy_metrics.strategy_id} | Delta: {delta:.2f}")
        return {
            "status": "SHADOW_TEST",
            "result": "PASS",
            "delta": round(delta, 2),
            "metrics": {
                "slippage": strategy_metrics.slippage,
                "fill_rate": strategy_metrics.fill_rate,
            },
        }

    def _update_avg_delta(self, delta: float) -> None:
        """Moving average update for all evaluated deltas."""
        n = self._stats["evaluated"]
        curr_avg = self._stats["avg_delta"]
        self._stats["avg_delta"] = curr_avg + (delta - curr_avg) / n

    def get_shadow_report(self) -> dict[str, Any]:
        """
        Generate high-level promotion telemetry.
        """
        total = self._stats["evaluated"]
        return {
            "status": "REPORT",
            "promotion_rate": round(self._stats["passed"] / total, 4) if total > 0 else 0.0,
            "avg_pnl_delta": round(self._stats["avg_delta"], 2),
        }
