from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig
_LOG = logging.getLogger("qtrader.execution.routing.cost_model")


class RoutingCostModel:
    def __init__(self, config: ExecutionConfig) -> None:
        self._config = config
        obj_cfg = getattr(config, "objective", {})
        self._impact_k = float(obj_cfg.get("impact_k", 0.1))
        self._base_fee = float(obj_cfg.get("base_fee", 0.0001))

    def estimate_costs(
        self,
        order_size: float,
        market_data: dict[str, dict[str, Any]],
        order_type: str = "MARKET",
        side: str = "BUY",
    ) -> dict[str, float]:
        if not market_data or order_size <= 0:
            return {}
        costs: dict[str, float] = {}
        for venue, orderbook in market_data.items():
            costs[venue] = float(
                self._calculate_venue_cost(venue, order_size, orderbook, order_type, side)
            )
        return costs

    def _calculate_venue_cost(
        self,
        venue_name: str,
        order_size: float,
        orderbook: dict[str, Any],
        order_type: str,
        side: str,
    ) -> float:
        try:
            levels = orderbook.get("asks" if side.upper() == "BUY" else "bids", [])
            best_price = float(levels[0][0]) if levels and len(levels[0]) > 0 else 1.0
            liquidity = float(levels[0][1]) if levels and len(levels[0]) > 1 else 1.0
            spread = float(orderbook.get("spread", 0.0))
            c_spread = spread / 2.0 * order_size
            c_slippage = self._impact_k * (order_size / liquidity) ** 2
            fee_rate = self._get_venue_fee_rate(venue_name, order_type)
            c_fee = order_size * best_price * fee_rate
            return float(c_spread + c_slippage + c_fee)
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error(f"RoutingCostModel: failed to compute cost for {venue_name}", exc_info=True)
            failsafe_penalty = 1e18
            return float(failsafe_penalty)

    def _get_venue_fee_rate(self, venue_name: str, order_type: str) -> float:
        exch_cfg = self._config.exchanges.get(venue_name, {})
        fees = exch_cfg.get("fees", {})
        fee_key = "taker" if order_type.upper() == "MARKET" else "maker"
        return float(fees.get(fee_key, self._base_fee))
