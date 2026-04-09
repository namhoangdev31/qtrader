from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig
_LOG = logging.getLogger("qtrader.execution.strategy.scheduler")

class ExecutionScheduler:
    def __init__(self, config: ExecutionConfig) -> None:
        sched_cfg = getattr(config, "routing", {}).get("scheduler", {})
        self._risk_aversion = float(sched_cfg.get("risk_aversion", 0.1))
        cm_cfg = getattr(config, "cost_model", {})
        self._eta = float(cm_cfg.get("impact_k", 0.15))

    def optimize_schedule(
        self, total_qty: float, predicted_states: list[dict[str, Any]]
    ) -> list[float]:
        if not predicted_states or total_qty <= 0:
            return []
        horizon_steps = len(predicted_states)
        if horizon_steps == 1:
            return [float(total_qty)]
        try:
            v_t = [max(1.0, float(s.get("liquidity", 1.0))) for s in predicted_states]
            s_t = [float(s.get("spread", 0.0)) for s in predicted_states]
            vol_t = [float(s.get("volatility", 0.0)) for s in predicted_states]
            c_t = [s_t[i] / 2.0 - self._risk_aversion * vol_t[i] for i in range(horizon_steps)]
            sum_v_eta = sum(v / self._eta for v in v_t)
            sum_cv_eta = sum(c_t[i] * v_t[i] / self._eta for i in range(horizon_steps))
            lam = (total_qty + sum_cv_eta) / sum_v_eta
            q_star = [max(0.0, (lam - c_t[i]) * v_t[i] / self._eta) for i in range(horizon_steps)]
            total_q_star = sum(q_star)
            tolerance = 1e-12
            if total_q_star > tolerance:
                multiplier = total_qty / total_q_star
                return [float(q * multiplier) for q in q_star]
            return [float(total_qty / horizon_steps)] * horizon_steps
        except Exception as e:
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("ExecutionScheduler: optimization failed, using TWAP", exc_info=True)
            return [float(total_qty / horizon_steps)] * horizon_steps

    def reset(self) -> None:
        pass