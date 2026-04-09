from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.strategy.scheduler")


class ExecutionScheduler:
    """
    Execution Scheduling Optimizer.

    Determines the mathematically optimal distribution of child-order quantities
    across a time horizon to minimize market impact and transaction costs.

    Objective:
    min sum(q_t * Cost(q_t, S_t))  s.t.  sum(q_t) = Q

    Model:
    Cost(q, S) = eta * (q/V)^2 [Impact] + spread/2 [Crossing] - gamma * vol [Delay]
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the scheduler with risk aversion and convergence parameters.
        """
        sched_cfg = getattr(config, "routing", {}).get("scheduler", {})
        self._risk_aversion = float(sched_cfg.get("risk_aversion", 0.1))

        # Pull impact coefficient from cost model (default to 0.15 as per cost_model.py)
        cm_cfg = getattr(config, "cost_model", {})
        self._eta = float(cm_cfg.get("impact_k", 0.15))

    def optimize_schedule(
        self, total_qty: float, predicted_states: list[dict[str, Any]]
    ) -> list[float]:
        """
        Compute the optimal child-order distribution using Lagrange optimization.

        Args:
            total_qty: Total parent quantity to execute.
            predicted_states: List of T market states (vol, liquidity, spread).

        Returns:
            List of child order quantities q_1 ... q_T.
        """
        if not predicted_states or total_qty <= 0:
            return []

        horizon_steps = len(predicted_states)
        if horizon_steps == 1:
            return [float(total_qty)]

        try:
            # Standard Almgren-Chriss extension for time-varying coefficients:
            # We solve for the optimal path where marginal costs are equal across steps.
            # Marginal Cost J'(q_t) = eta * q_t / V_t + Spread_t/2 - gamma * Vol_t = lambda

            v_t = [max(1.0, float(s.get("liquidity", 1.0))) for s in predicted_states]
            s_t = [float(s.get("spread", 0.0)) for s in predicted_states]
            vol_t = [float(s.get("volatility", 0.0)) for s in predicted_states]

            # Step-specific constant costs (Intercepts of the marginal cost curve)
            c_t = [(s_t[i] / 2.0) - (self._risk_aversion * vol_t[i]) for i in range(horizon_steps)]

            # Solving sum(q_t) = Q => sum((lambda - c_t) * v_t / eta) = Q
            # lambda * sum(v_t/eta) - sum(c_t * v_t/eta) = Q
            sum_v_eta = sum(v / self._eta for v in v_t)
            sum_cv_eta = sum((c_t[i] * v_t[i]) / self._eta for i in range(horizon_steps))

            # Derive shadow price (Lagrange multiplier)
            lam = (total_qty + sum_cv_eta) / sum_v_eta

            # Extract final optimal quantities (enforcing non-negativity)
            q_star = [max(0.0, (lam - c_t[i]) * v_t[i] / self._eta) for i in range(horizon_steps)]

            # Structural re-normalization to compensate for rounding or zero-floor clipping
            total_q_star = sum(q_star)
            tolerance = 1e-12
            if total_q_star > tolerance:
                multiplier = total_qty / total_q_star
                return [float(q * multiplier) for q in q_star]

            # Failsafe: Uniform TWAP fallback if optimizer results in zero everywhere
            return [float(total_qty / horizon_steps)] * horizon_steps

        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("ExecutionScheduler: optimization failed, using TWAP", exc_info=True)
            return [float(total_qty / horizon_steps)] * horizon_steps

    def reset(self) -> None:
        """Reset internal optimizer state."""
        pass
