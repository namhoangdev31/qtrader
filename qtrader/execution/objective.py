from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from qtrader.core.events import ExecutionObjectiveEvent, ExecutionObjectivePayload
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.execution.config import ExecutionConfig


class ExecutionObjective:
    """
    Global Execution Optimization Objective Function (J).

    Defines the unified cost minimization target for all execution strategies:
    - Impact Cost: Market impact based on size vs liquidity.
    - Timing Cost: Opportunity cost and delay risk.
    - Fees & Spread: Explicit and implicit transaction costs.
    - Risk Penalty: Variance of PnL across potential execution paths.

    Mathematical Model:
    J = E[C_impact + C_timing + C_fees + C_risk]
    """

    def __init__(self, config: ExecutionConfig, event_bus: EventBus | None = None) -> None:
        """
        Initialize the objective function with calibrated parameters.
        """
        self._config = config
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

        # Calibration Parameters
        obj_cfg = config.objective
        self._k = float(obj_cfg.get("impact_k", 0.1))
        self._alpha = float(obj_cfg.get("impact_alpha", 0.5))
        self._lambda = float(obj_cfg.get("timing_lambda", 0.01))
        self._gamma = float(obj_cfg.get("risk_gamma", 0.1))
        self._base_fee = float(obj_cfg.get("base_fee", 0.0001))

    async def compute(
        self, state: dict[str, Any], action: dict[str, Any], strategy_id: str = "GLOBAL"
    ) -> float:
        """
        Compute the total scalar cost J(S_t, a_t).

        Args:
            state: Market state vector (liquidity, volatility, spread).
            action: Execution action (order_size, venue, urgency).
            strategy_id: Identifier for auditing.
        """
        try:
            # 1. Cost Components
            c_impact = self.compute_impact(state, action)
            c_timing = self.compute_timing(state, action)
            c_fees = self.compute_fees(state, action)
            c_risk = self.compute_risk(state, action)

            total_cost = float(c_impact + c_timing + c_fees + c_risk)

            # 2. Auditing & Reporting
            if self._event_bus:
                event = ExecutionObjectiveEvent(
                    trace_id=self._system_trace,
                    source="ExecutionObjective",
                    payload=ExecutionObjectivePayload(
                        strategy_id=strategy_id,
                        symbol=str(state.get("symbol", "UNKNOWN")),
                        total_cost=total_cost,
                        impact_cost=float(c_impact),
                        timing_cost=float(c_timing),
                        fee_cost=float(c_fees),
                        risk_cost=float(c_risk),
                        metadata={"action": action, "market_state_keys": list(state.keys())},
                    ),
                )
                await self._event_bus.publish(event)

            return total_cost

        except Exception as e:
            logger.error(f"OBJECTIVE_COMPUTE_FAILURE | {strategy_id} | {e!s}")
            # return a large finite float to satisfy mypy and represent high cost
            return 1e18

    def compute_impact(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Impact Cost: C_impact = k * (order_size / liquidity)^alpha."""
        order_size = float(action.get("order_size", 0.0))
        liquidity = float(state.get("liquidity", 1.0))  # Avoid division by zero
        if liquidity <= 0:
            liquidity = 1.0
        return cast("float", self._k * (order_size / liquidity) ** self._alpha)

    def compute_impact_derivative(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Impact Derivative with respect to order_size (optional for RL)."""
        order_size = float(action.get("order_size", 0.0))
        liquidity = float(state.get("liquidity", 1.0))
        if order_size <= 0:
            return 0.0
        # d/dx k*(x/L)^a = k * a * (x/L)^(a-1) * (1/L)
        impact_grad = self._k * self._alpha * (order_size / liquidity) ** (self._alpha - 1.0)
        return cast("float", impact_grad * (1.0 / liquidity))

    def compute_timing(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Timing Cost: C_timing = lambda * delay."""
        delay = float(action.get("delay", 0.0))
        return self._lambda * delay

    def compute_fees(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Fees & Spread: C_fees = base_fee + spread_cost."""
        spread = float(state.get("spread_pct", 0.0))
        order_size = float(action.get("order_size", 0.0))
        return (self._base_fee * order_size) + (spread * order_size / 2.0)

    def compute_risk(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Risk Penalty: C_risk = gamma * Var(PnL)."""
        volatility = float(state.get("volatility", 0.0))
        order_size = float(action.get("order_size", 0.0))
        # Simple risk model: Var(PnL) proportional to size^2 * vol^2
        variance_pnl = (order_size * volatility) ** 2
        return self._gamma * variance_pnl
