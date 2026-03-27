from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import polars as pl  # noqa: TC002

_LOG = logging.getLogger("qtrader.meta.approval_system")


@dataclass(slots=True, frozen=True)
class ApprovalMetrics:
    """
    Industrial Metrics Container for strategic deployment sign-off.
    """

    strategy_id: str
    sharpe: float
    mdd: float  # Absolute Maximum Drawdown (e.g. 0.15 for 15%)
    win_rate: float
    turnover: float
    returns: pl.Series  # Daily or High-frequency return series for Stability analysis


class StrategyApprovalSystem:
    """
    Principal Institutional Approval Committee.

    Evaluates alpha candidates against a deterministic multi-factor scoring model
    and hard risk-governance constraints. Acts as the terminal gatekeeper for
    authorizing capitalization and live transitions.
    """

    def __init__(
        self,
        min_sharpe: float = 1.5,
        max_dd: float = 0.15,
        min_stability: float = 1.0,
        approval_threshold: float = 2.0,
        weights: dict[str, float] | None = None,
    ) -> None:
        """
        Initialize the Committee parameters and weighting factors.

        Args:
            min_sharpe: Absolute minimum required Sharpe ratio.
            max_dd: Absolute maximum allowable drawdown (decimal).
            min_stability: Minimum relative stability (1/Var).
            approval_threshold: Composite score required for formal approval.
            weights: Dictionary of scoring weights for the multi-factor model.
        """
        self._min_sharpe = min_sharpe
        self._max_dd = max_dd
        self._min_stability = min_stability
        self._approval_threshold = approval_threshold

        # Default Industrial Weights
        self._weights = weights or {
            "sharpe": 1.0,
            "stability": 0.5,
            "win_rate": 0.5,
            "mdd": -2.0,  # Highly penalize heavy drawdown
            "turnover": -0.3,  # Slight penalty for execution friction
        }

        # Telemetry
        self._stats = {"evaluated": 0, "approved": 0, "avg_approved_score": 0.0}

    def evaluate(self, metrics: ApprovalMetrics) -> dict[str, Any]:
        """
        Conduct a formal strategic review of the candidate signal.

        Args:
            metrics: Standardized performance and risk metrics.

        Returns:
            Approval decision, composite score, and optional rejection context.
        """
        self._stats["evaluated"] += 1

        # 1. Stability Calculation: Inverse Annualized Volatility
        # We normalize to prevent Variance (10^-6) from drowning out Sharpe
        ret_std_val = metrics.returns.std()
        ret_std = float(ret_std_val) if isinstance(ret_std_val, (int, float)) else 0.0
        annual_vol = ret_std * (252**0.5)
        stability = 1.0 / annual_vol if annual_vol > 1e-6 else 0.0  # noqa: PLR2004

        # 2. Hard Constraint Filters: The 'Blackball' Rejection Gates
        rejections: list[str] = []
        if metrics.sharpe < self._min_sharpe:
            rejections.append(f"SHARPE_LOW:{metrics.sharpe:.2f}")
        if metrics.mdd > self._max_dd:
            rejections.append(f"MDD_HIGH:{metrics.mdd:.2f}")
        if stability < self._min_stability:
            rejections.append(f"STABILITY_LOW:{stability:.2f}")

        if rejections:
            _LOG.info(f"REJECTED | {metrics.strategy_id} | Gates: {', '.join(rejections)}")
            return {
                "status": "DECISION",
                "decision": "REJECTED",
                "score": 0.0,
                "reason": "; ".join(rejections),
            }

        # 3. Composite Scoring Model
        score = (
            (self._weights["sharpe"] * metrics.sharpe)
            + (self._weights["stability"] * stability)
            + (self._weights["win_rate"] * metrics.win_rate)
            + (self._weights["mdd"] * metrics.mdd)
            + (self._weights["turnover"] * metrics.turnover)
        )

        # 4. Final Threshold Consensus
        if score >= self._approval_threshold:
            self._stats["approved"] += 1
            n = self._stats["approved"]
            curr_avg = self._stats["avg_approved_score"]
            self._stats["avg_approved_score"] = curr_avg + (score - curr_avg) / n

            _LOG.info(f"APPROVED | {metrics.strategy_id} | Score: {score:.2f}")
            return {"status": "DECISION", "decision": "APPROVED", "score": round(score, 2)}

        _LOG.info(
            f"REJECTED | {metrics.strategy_id} | Score {score:.2f} < {self._approval_threshold}"
        )
        return {
            "status": "DECISION",
            "decision": "REJECTED",
            "score": round(score, 2),
            "reason": "INSUFFICIENT_COMPOSITE_SCORE",
        }

    def get_approval_report(self) -> dict[str, Any]:
        """
        Generate high-level committee governance report.
        """
        total = self._stats["evaluated"]
        approved = self._stats["approved"]

        return {
            "status": "REPORT",
            "approval_rate": round(approved / total, 4) if total > 0 else 0.0,
            "avg_approved_score": round(self._stats["avg_approved_score"], 2),
        }
