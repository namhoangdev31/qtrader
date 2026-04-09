from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig
_LOG = logging.getLogger("qtrader.execution.rl.reward")

class ExecutionRewardFunction:
    def __init__(self, config: ExecutionConfig) -> None:
        self._config = config
        rl_cfg = getattr(config, "rl", {}).get("reward", {})
        self._beta = float(rl_cfg.get("fill_bonus_weight", 0.5))
        self._gamma = float(rl_cfg.get("toxicity_penalty_weight", 0.2))

    def compute(self, execution_result: dict[str, Any], market_state: dict[str, Any]) -> float:
        try:
            cost = float(execution_result.get("total_cost", 0.0))
            order_value = float(execution_result.get("order_value", 0.0))
            min_val = 1e-12
            if order_value > min_val:
                bps_scale = 10000.0
                r_cost = -(cost / order_value) * bps_scale
            else:
                r_cost = 0.0
            filled = float(execution_result.get("filled_qty", 0.0))
            total = float(execution_result.get("total_qty", 1.0))
            fill_rate = filled / max(1e-09, total)
            r_fill = self._beta * fill_rate
            toxicity = float(market_state.get("toxicity_score", 0.0))
            r_toxic = -self._gamma * toxicity
            total_reward = float(r_cost + r_fill + r_toxic)
            reward_cap = 1000.0
            return float(max(-reward_cap, min(reward_cap, total_reward)))
        except Exception as e:
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("ExecutionRewardFunction: failed to compute reward", exc_info=True)
            return 0.0