from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from scipy import stats


_LOG = logging.getLogger("qtrader.ml.model_comparator")


class ScalableModel(Protocol):
    """
    Structural interface for ML models to be compared.
    Ensures that any object with a 'predict' method can be evaluated.
    """

    def predict(self, x_data: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """Generate point predictions for validation data."""
        ...


@dataclass(slots=True, frozen=True)
class ComparisonResult:
    """
    Industrial Model Comparison Summary.
    """

    decision: str  # PROMOTE / REJECT
    mse_delta: float  # Absolute improvement in MSE
    sharpe_delta: float  # Absolute change in Sharpe ratio
    p_value: float  # Significance of MSE improvement
    is_statistically_significant: bool


class ModelComparator:
    """
    Principal Model Comparison Engine.

    Objective: Enforce a terminal statistical gate for model promotion.
    Theta_new is ONLY promoted if it demonstrates statistically significant
    MSE improvement (p < 0.05) and no critical Sharpe degradation.
    Ensures that promotion is driven by signal, not white noise.
    """

    def __init__(self, alpha: float = 0.05, sharpe_safety_buffer: float = 0.05) -> None:
        """
        Initialize the comparison gate parameters.

        Args:
            alpha: Significance level for the paired t-test (default: 0.05).
            sharpe_safety_buffer: Max % Sharpe degradation allowed during promotion.
        """
        self._alpha = alpha
        self._sharpe_buffer = sharpe_safety_buffer

        # Telemetry
        self._stats = {"promotions": 0, "comparisons": 0}

    def _calculate_sharpe(self, returns: np.ndarray[Any, Any]) -> float:
        """
        Compute annualized Sharpe ratio assuming daily periodicity.
        """
        if len(returns) < 2:  # noqa: PLR2004
            return 0.0

        avg = np.mean(returns)
        std = np.std(returns)

        if std < 1e-9:  # noqa: PLR2004
            return 0.0

        # Annualization factor for daily data (sqrt(252))
        return float(avg / std * np.sqrt(252))

    def compare(
        self,
        old_model: ScalableModel,
        new_model: ScalableModel,
        x_val: np.ndarray[Any, Any],
        y_val: np.ndarray[Any, Any],
    ) -> ComparisonResult:
        """
        Execute the statistical comparison protocol between two models.

        Process:
        1. Generate out-of-sample predictions.
        2. Calculate Mean Squared Error (MSE) and Sharpe deltas.
        3. Perform Paired t-test on squared residuals to verify improvement significance.
        4. Enforce hard constraints (Sharpe buffer).

        Returns:
            ComparisonResult containing the promotion decision and metrics.
        """
        self._stats["comparisons"] += 1

        # 1. Prediction Generation
        pred_old = old_model.predict(x_val)
        pred_new = new_model.predict(x_val)

        # 2. Residual Analysis
        err_old = pred_old - y_val
        err_new = pred_new - y_val

        mse_old = np.mean(err_old**2)
        mse_new = np.mean(err_new**2)
        mse_delta = mse_old - mse_new  # Positive is improvement

        # 3. Alpha Analysis (Assuming y_val relates to returns)
        sharpe_old = self._calculate_sharpe(pred_old)
        sharpe_new = self._calculate_sharpe(pred_new)
        sharpe_delta = sharpe_new - sharpe_old

        # 4. Statistical Significance Test (Paired t-test on Squared Errors)
        # Null Hypothesis (H0): mean(sq_err_new) >= mean(sq_err_old)
        # Alternative (H1): mean(sq_err_new) < mean(sq_err_old)
        _, p_val = stats.ttest_rel(err_new**2, err_old**2, alternative="less")
        p_val_float = float(p_val)
        is_significant = p_val_float < self._alpha

        # 5. Terminal Decision Logic
        # PROMOTE if (significant improvement) AND (no sharpe degradation beyond buffer)
        decision = "REJECT"
        if is_significant and sharpe_new >= sharpe_old * (1.0 - self._sharpe_buffer):
            decision = "PROMOTE"
            self._stats["promotions"] += 1
            _LOG.info(
                f"[COMPARISON] PROMOTE | MSE_delta: {mse_delta:.6f} | p: {p_val_float:.4f}"
            )
        else:
            reason = "NOT_SIGNIFICANT" if not is_significant else "SHARPE_DEGRADATION"
            _LOG.warning(f"[COMPARISON] REJECT | Reason: {reason} | p: {p_val_float:.4f}")

        return ComparisonResult(
            decision=decision,
            mse_delta=round(float(mse_delta), 6),
            sharpe_delta=round(float(sharpe_delta), 4),
            p_value=round(p_val_float, 4),
            is_statistically_significant=is_significant,
        )

    def get_comparison_report(self) -> dict[str, Any]:
        """
        Generate high-level comparison telemetry summary.
        """
        total = self._stats["comparisons"]
        return {
            "status": "REPORT",
            "total_comparisons": total,
            "promotion_rate": (
                round(self._stats["promotions"] / total, 4) if total > 0 else 0.0
            ),
        }
