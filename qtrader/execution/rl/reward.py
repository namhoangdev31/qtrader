from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.rl.reward")


class ExecutionRewardFunction:
    """
    Execution Reward Function for Reinforcement Learning.

    Translates multi-dimensional execution performance (Cost, Fill Rate, Toxicity)
    into a scalar learning signal for the RL agent.

    Mathematical Model:
    R_t = -Standardized_Cost + (beta * Fill_Rate) - (gamma * Toxicity_Score)

    Where:
    - Standardized_Cost: Implementation Shortfall in basis points (bps).
    - Fill_Rate: Proportion of targeted volume successfully executed.
    - Toxicity_Score: Exposure to informed trade flow (adverse selection).
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the reward function with calibrated weighting parameters.
        """
        self._config = config

        # RL Reward Parameters from ExecutionConfig
        # Alignment: Multi-objective balance between cost minimization and fill certainty.
        rl_cfg = getattr(config, "rl", {}).get("reward", {})
        self._beta = float(rl_cfg.get("fill_bonus_weight", 0.5))
        self._gamma = float(rl_cfg.get("toxicity_penalty_weight", 0.2))

    def compute(self, execution_result: dict[str, Any], market_state: dict[str, Any]) -> float:
        """
        Compute the scalar reward R_t for an execution episode/step.

        Args:
            execution_result: Mapping containing metrics (cost, value, qty).
            market_state: Mapping containing 'toxicity_score' (0.0 to 1.0).

        Returns:
            Scalar reward R_t.
        """
        try:
            # Primary Penalty: Implementation Shortfall in bps.
            cost = float(execution_result.get("total_cost", 0.0))
            order_value = float(execution_result.get("order_value", 0.0))

            min_val = 1e-12
            if order_value > min_val:
                # 10,000 multiplier to convert relative cost to basis points (bps)
                bps_scale = 10000.0
                r_cost = -(cost / order_value) * bps_scale
            else:
                # If no trade occurred/value is zero, cost is zero
                r_cost = 0.0

            # 2. Fill Component (Success Bonus)
            # Penalizes opportunity cost of unexecuted volume.
            filled = float(execution_result.get("filled_qty", 0.0))
            total = float(execution_result.get("total_qty", 1.0))
            fill_rate = filled / max(1e-9, total)
            r_fill = self._beta * fill_rate

            # 3. Toxicity Component (Adverse Selection Penalty)
            # Penalizes the agent for trading into toxic informed flow.
            toxicity = float(market_state.get("toxicity_score", 0.0))
            r_toxic = -self._gamma * toxicity

            # 4. Normalized Aggregate Scalar Reward
            total_reward = float(r_cost + r_fill + r_toxic)

            # High-performance sanity check: Clip extreme rewards to prevent weight shocks
            reward_cap = 1000.0
            return float(max(-reward_cap, min(reward_cap, total_reward)))

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("ExecutionRewardFunction: failed to compute reward", exc_info=True)
            # Silent failover to zero reward (neutral signal) to avoid crashing RL update loop
            return 0.0
