
from qtrader.backtest.impact import MarketImpactModel
from qtrader.core.config import Config
from qtrader.core.event import OrderEvent
from qtrader.execution.oms import UnifiedOMS


class SmartOrderRouter:
    """
    Finds the best venue(s) for a given order based on liquidity and price.
    """
    
    def __init__(self, oms: UnifiedOMS) -> None:
        self.oms = oms

    async def get_best_venue(self, symbol: str, side: str) -> str:
        """
        Logic to poll orderbooks from multiple venues and pick the best one.
        (v4.3: prefer lowest expected execution cost = price + impact; fallback to cached liquidity)
        """
        side_u = side.upper()

        best_venue: str | None = None
        best_cost: float | None = None
        best_depth = -1.0

        ctx = self.oms.get_pending_order_context(symbol)
        order_size = float(ctx.get("order_size", 0.0) or 0.0)
        default_daily_volume = float(ctx.get("daily_volume", Config.IMPACT_DAILY_VOLUME) or Config.IMPACT_DAILY_VOLUME)
        default_sigma_daily = float(ctx.get("sigma_daily", Config.IMPACT_SIGMA_DAILY) or Config.IMPACT_SIGMA_DAILY)
        impact_y = float(ctx.get("impact_y", Config.IMPACT_Y) or Config.IMPACT_Y)

        for name in self.oms.adapters.keys():
            state = self.oms.get_market_state(name, symbol)
            bid = float(state.get("bid", 0.0) or 0.0)
            ask = float(state.get("ask", 0.0) or 0.0)
            bid_size = float(state.get("bid_size", 0.0) or 0.0)
            ask_size = float(state.get("ask_size", 0.0) or 0.0)
            top_depth = float(state.get("top_depth", 0.0) or 0.0)
            daily_volume = float(state.get("daily_volume", default_daily_volume) or default_daily_volume)
            sigma_daily = float(state.get("sigma_daily", default_sigma_daily) or default_sigma_daily)

            if side_u == "BUY":
                px = ask if ask > 0 else None
                depth = top_depth or ask_size
                impact_bps = MarketImpactModel.square_root_impact(
                    order_size=order_size,
                    daily_vol=daily_volume,
                    daily_volume=daily_volume,
                    sigma_daily=sigma_daily,
                    y=impact_y,
                )
                cost = px * (1.0 + impact_bps / 10000.0) if px is not None else None
                is_better = cost is not None and (best_cost is None or cost < best_cost)
            else:
                px = bid if bid > 0 else None
                depth = top_depth or bid_size
                impact_bps = MarketImpactModel.square_root_impact(
                    order_size=order_size,
                    daily_vol=daily_volume,
                    daily_volume=daily_volume,
                    sigma_daily=sigma_daily,
                    y=impact_y,
                )
                cost = px * (1.0 - impact_bps / 10000.0) if px is not None else None
                is_better = cost is not None and (best_cost is None or cost > best_cost)

            if is_better or (cost is not None and best_cost == cost and depth > best_depth):
                best_cost = cost
                best_venue = name
                best_depth = depth

        if best_venue is not None:
            return best_venue

        # Fallback: venue with highest cached balance as proxy for capacity.
        best_venue = None
        max_liquidity = -1.0
        for name in self.oms.adapters.keys():
            balance = float(self.oms.positions.get(name, {}).get("USDT", 0.0) or 0.0)
            if balance > max_liquidity:
                max_liquidity = balance
                best_venue = name

        return best_venue or list(self.oms.adapters.keys())[0]

    async def split_order(self, order: OrderEvent, venues: list[str]) -> list[tuple[str, OrderEvent]]:
        """Splits a large order into multiple venues (Arbitrage/Liquidity capture)."""
        # Logic for proportioning order size based on book depth
        portions = []
        qty_per_venue = order.quantity / len(venues)
        for v in venues:
            new_order = OrderEvent(
                symbol=order.symbol,
                side=order.side,
                quantity=qty_per_venue,
                order_type=order.order_type,
                price=order.price
            )
            portions.append((v, new_order))
        return portions
