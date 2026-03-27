from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.routing.cost_model")


class RoutingCostModel:
    """
    Routing Cost Model.

    Estimates execution cost per venue to drive optimal order routing.
    Factors in implicit costs (Spread, Slippage) and explicit costs (Fees).

    Mathematical Model:
    C_v = (spread / 2) * size [Spread] + k * (size/liq)^2 [Slippage] + fee * value [Fees]
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the routing cost model with global parameters.
        """
        self._config = config

        # Base parameters from global configuration
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
        """
        Estimate total transaction costs for all available venues.

        Args:
            order_size: Targeted order quantity.
            market_data: Venue-specific orderbook snapshots.
            order_type: 'MARKET' or 'LIMIT'.
            side: 'BUY' or 'SELL'.

        Returns:
            Dictionary mapping venue_name -> estimated absolute total cost.
        """
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
        """
        Internal decomposition of venue-specific costs.
        """
        try:
            # 1. Price & Liquidity Components
            # Asks for BUY, Bids for SELL
            levels = orderbook.get("asks" if side.upper() == "BUY" else "bids", [])
            best_price = float(levels[0][0]) if (levels and len(levels[0]) > 0) else 1.0
            liquidity = float(levels[0][1]) if (levels and len(levels[0]) > 1) else 1.0

            # 2. Spread Cost (Implicit Crossing Cost)
            spread = float(orderbook.get("spread", 0.0))
            c_spread = (spread / 2.0) * order_size

            # 3. Slippage Cost (Quadratic Market Impact)
            c_slippage = self._impact_k * (order_size / liquidity) ** 2

            # 4. Fee Cost (Explicit Transaction Charge)
            fee_rate = self._get_venue_fee_rate(venue_name, order_type)
            c_fee = (order_size * best_price) * fee_rate

            return float(c_spread + c_slippage + c_fee)

        except Exception:
            _LOG.error(f"RoutingCostModel: failed to compute cost for {venue_name}", exc_info=True)
            # Return effectively infinite cost for failed prediction to discourage venue selection
            failsafe_penalty = 1e18
            return float(failsafe_penalty)

    def _get_venue_fee_rate(self, venue_name: str, order_type: str) -> float:
        """
        Retrieve venue-specific fee or fallback to baseline from objective.
        """
        # Search in exchange adapters config for venue-specific fees
        exch_cfg = self._config.exchanges.get(venue_name, {})
        fees = exch_cfg.get("fees", {})

        # Default key selection for Maker vs Taker
        # MARKET orders always take liquidity -> Taker fee
        fee_key = "taker" if order_type.upper() == "MARKET" else "maker"
        return float(fees.get(fee_key, self._base_fee))
