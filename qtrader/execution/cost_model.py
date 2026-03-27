from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from qtrader.core.events import ExecutionCostEvent, ExecutionCostPayload
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.execution.config import ExecutionConfig


class CostModel:
    """
    Forensic Execution Cost Appraisal Model.

    Decomposes execution costs into 4 dimensions for precise attribution:
    1. Impact Cost: Quadratic market impact based on size vs liquidity.
    2. Timing Cost: Opportunity cost and delay risk based on volatility.
    3. Spread Cost: Implicit cost of crossing the bid-ask spread.
    4. Fees: Explicit transaction costs (Fixed + Proportional).

    Calculated total aligns with Implementation Shortfall (IS).
    """

    def __init__(self, config: ExecutionConfig, event_bus: EventBus | None = None) -> None:
        """
        Initialize the cost model with calibrated parameters.
        """
        self._config = config
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

        # Calibration Parameters
        cm_cfg = config.cost_model
        self._k = float(cm_cfg.get("impact_k", 0.15))
        self._timing_alpha = float(cm_cfg.get("timing_alpha", 0.05))
        self._fixed_fee = float(cm_cfg.get("fixed_fee", 1.0))
        self._prop_fee = float(cm_cfg.get("prop_fee", 0.0002))

    async def compute(
        self, state: dict[str, Any], action: dict[str, Any], strategy_id: str = "GLOBAL"
    ) -> dict[str, float]:
        """
        Compute the full cost decomposition for an execution decision.

        Args:
            state: Market state (liquidity, volatility, spread, price).
            action: Execution action (order_size, delay, venue).
            strategy_id: Identifier for auditing.
        """
        try:
            # 1. Component Extraction
            size = float(action.get("order_size", 0.0))
            price = float(state.get("price", 0.0))
            if price <= 0:
                price = float(state.get("mid", 0.0))

            # 2. Compute Components
            c_impact = self._compute_impact(state, action)
            c_timing = self._compute_timing(state, action)
            c_spread = self._compute_spread(state, action)
            c_fees = self._compute_fees(size, price)

            total_cost = float(c_impact + c_timing + c_spread + c_fees)

            # 3. Auditing & Reporting
            if self._event_bus:
                event = ExecutionCostEvent(
                    trace_id=self._system_trace,
                    source="CostModel",
                    payload=ExecutionCostPayload(
                        symbol=str(state.get("symbol", "UNKNOWN")),
                        total_cost=total_cost,
                        impact_cost=float(c_impact),
                        timing_cost=float(c_timing),
                        spread_cost=float(c_spread),
                        fee_cost=float(c_fees),
                        metadata={
                            "strategy_id": strategy_id,
                            "action": action,
                        },
                    ),
                )
                await self._event_bus.publish(event)

            return {
                "total_cost": total_cost,
                "impact_cost": c_impact,
                "timing_cost": c_timing,
                "spread_cost": c_spread,
                "fee_cost": c_fees,
            }

        except Exception as e:
            logger.error(f"COST_MODEL_COMPUTE_FAILURE | {strategy_id} | {e!s}")
            return {
                "total_cost": float("1e18"),
                "impact_cost": 0.0,
                "timing_cost": 0.0,
                "spread_cost": 0.0,
                "fee_cost": 0.0,
            }

    def _compute_impact(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Quadratic Market Impact: C_impact = k * (size / liquidity)^2."""
        size = float(action.get("order_size", 0.0))
        liquidity = float(state.get("liquidity", 0.0))
        if liquidity <= 0:
            liquidity = 1.0  # Failsafe estimation
        return self._k * (size / liquidity) ** 2

    def _compute_timing(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Timing Risk/Opportunity Cost: C_timing = alpha * vol * delay."""
        vol = float(state.get("volatility", 0.0))
        delay = float(action.get("delay", 0.0))
        return self._timing_alpha * vol * delay

    def _compute_spread(self, state: dict[str, Any], action: dict[str, Any]) -> float:
        """Spread Cost: C_spread = (Spread / 2) * Size (Relative or Absolute)."""
        spread = float(state.get("spread", 0.0))
        size = float(action.get("order_size", 0.0))
        return (spread / 2.0) * size

    def _compute_fees(self, size: float, price: float) -> float:
        """Explicit Fees: C_fees = fixed + (prop_fee * value)."""
        value = size * price
        return self._fixed_fee + (self._prop_fee * value)
