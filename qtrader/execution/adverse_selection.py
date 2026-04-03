"""Adverse Selection Modeling — Standash §4.7.

Estimates probability of adverse selection: a fill followed by a price move
against the position. Uses VPIN (Volume-Synchronized Probability of Informed
Trading) and orderbook imbalance signals.

Model: P(adverse) = sigmoid(α * imbalance + β * delta_p + γ * fill_rate + δ * vpin + intercept)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import polars as pl


@dataclass(slots=True)
class AdverseModelParams:
    """Parameters for the adverse selection model."""

    alpha: float = 1.0  # Weight for orderbook imbalance
    beta: float = 1.0  # Weight for price movement (delta_p)
    gamma: float = 1.0  # Weight for fill rate
    delta: float = 0.5  # Weight for VPIN toxicity score
    intercept: float = 0.0


@dataclass(slots=True)
class AdverseSelectionResult:
    """Result of adverse selection analysis."""

    probability: float
    imbalance: float
    delta_p: float
    fill_rate: float
    vpin_score: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL


class AdverseSelectionModel:
    """Adverse Selection Model — Standash §4.7.

    Estimates probability that an executed fill will be followed by a price
    move against the position (adverse selection).

    Signals used:
    - Orderbook imbalance (bid vs ask volume)
    - Recent price momentum (delta_p)
    - Fill rate (executed vs placed volume)
    - VPIN toxicity score (informed trading probability)
    """

    def __init__(self, params: AdverseModelParams | None = None) -> None:
        self.params = params or AdverseModelParams()
        self._history: list[AdverseSelectionResult] = []
        self._max_history = 10_000

    @staticmethod
    def sigmoid(x: float) -> float:
        """Numerically stable sigmoid function."""
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)

    def estimate_probability(
        self,
        imbalance: float,
        delta_p: float,
        fill_rate: float,
        vpin_score: float = 0.0,
    ) -> AdverseSelectionResult:
        """Estimate P(adverse) for a single observation.

        Args:
            imbalance: Orderbook imbalance in [-1, 1].
            delta_p: Recent price movement (normalized).
            fill_rate: Fill rate [0, 1].
            vpin_score: VPIN toxicity score [0, 1].

        Returns:
            AdverseSelectionResult with probability and risk level.
        """
        score = (
            self.params.alpha * imbalance
            + self.params.beta * delta_p
            + self.params.gamma * fill_rate
            + self.params.delta * vpin_score
            + self.params.intercept
        )
        probability = self.sigmoid(score)

        # Classify risk level
        if probability < 0.25:
            risk_level = "LOW"
        elif probability < 0.50:
            risk_level = "MEDIUM"
        elif probability < 0.75:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"

        result = AdverseSelectionResult(
            probability=probability,
            imbalance=imbalance,
            delta_p=delta_p,
            fill_rate=fill_rate,
            vpin_score=vpin_score,
            risk_level=risk_level,
        )

        # Track history
        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history // 2 :]

        return result

    def estimate_batch(self, df: pl.DataFrame) -> pl.DataFrame:
        """Vectorized probability estimation for a batch of observations.

        Input df must contain: imbalance, delta_p, fill_rate.
        Optionally contains: vpin_score.
        Adds 'p_adverse' and 'risk_level' columns.
        """
        vpin_col = "vpin_score" if "vpin_score" in df.columns else None

        # Linear score
        score_expr = (
            pl.lit(self.params.alpha) * pl.col("imbalance")
            + pl.lit(self.params.beta) * pl.col("delta_p")
            + pl.lit(self.params.gamma) * pl.col("fill_rate")
        )
        if vpin_col:
            score_expr += pl.lit(self.params.delta) * pl.col(vpin_col)
        score_expr += pl.lit(self.params.intercept)

        # Sigmoid: 1 / (1 + exp(-score))
        df = df.with_columns(
            [
                (1.0 / (1.0 + (-score_expr).exp())).alias("p_adverse"),
            ]
        )

        # Risk level classification
        df = df.with_columns(
            [
                pl.when(pl.col("p_adverse") < 0.25)
                .then(pl.lit("LOW"))
                .when(pl.col("p_adverse") < 0.50)
                .then(pl.lit("MEDIUM"))
                .when(pl.col("p_adverse") < 0.75)
                .then(pl.lit("HIGH"))
                .otherwise(pl.lit("CRITICAL"))
                .alias("risk_level"),
            ]
        )

        return df

    def compute_vpin(
        self,
        buy_volume: pl.Series,
        sell_volume: pl.Series,
        bucket_count: int = 50,
    ) -> float:
        """Compute VPIN (Volume-Synchronized Probability of Informed Trading).

        VPIN measures the imbalance between buy and sell volume over
        volume buckets. High VPIN indicates informed trading flow.

        Args:
            buy_volume: Series of buy volumes per bucket.
            sell_volume: Series of sell volumes per bucket.
            bucket_count: Number of recent buckets to use.

        Returns:
            VPIN score in [0, 1].
        """
        if len(buy_volume) == 0 or len(sell_volume) == 0:
            return 0.0

        # Use recent buckets
        bv = buy_volume.tail(bucket_count)
        sv = sell_volume.tail(bucket_count)

        total_volume = (bv + sv).sum()
        if total_volume == 0:
            return 0.0

        order_flow_imbalance = (bv - sv).abs().sum()
        vpin = float(order_flow_imbalance / total_volume)

        return min(1.0, max(0.0, vpin))

    def get_calibration_stats(self) -> dict[str, Any]:
        """Return calibration statistics from historical predictions."""
        if not self._history:
            return {"count": 0}

        probs = [r.probability for r in self._history]
        return {
            "count": len(self._history),
            "mean_probability": sum(probs) / len(probs),
            "max_probability": max(probs),
            "min_probability": min(probs),
            "critical_count": sum(1 for r in self._history if r.risk_level == "CRITICAL"),
            "high_count": sum(1 for r in self._history if r.risk_level == "HIGH"),
            "params": {
                "alpha": self.params.alpha,
                "beta": self.params.beta,
                "gamma": self.params.gamma,
                "delta": self.params.delta,
                "intercept": self.params.intercept,
            },
        }

    def update_params(self, **kwargs: float) -> None:
        """Update model parameters for calibration."""
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)
