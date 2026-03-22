from typing import Any

from qtrader.core.event import MarketDataEvent
from qtrader.execution.oms import UnifiedOMS

try:
    from qtrader.execution.orderbook_core import OrderbookEngine  # type: ignore
except Exception:  # pragma: no cover
    OrderbookEngine = None  # type: ignore


def _compute_micro_features_py(state: dict[str, Any]) -> dict[str, float]:
    bid = float(state.get("bid", 0.0) or 0.0)
    ask = float(state.get("ask", 0.0) or 0.0)
    bid_size = float(state.get("bid_size", 0.0) or 0.0)
    ask_size = float(state.get("ask_size", 0.0) or 0.0)
    if ask <= 0:
        return {"micro_spread": 0.0, "micro_imbalance": 0.0, "micro_mid": 0.0}
    spread = (ask - bid) / ask
    denom = bid_size + ask_size
    imbalance = (bid_size - ask_size) / denom if denom > 0 else 0.0
    mid = (bid + ask) / 2.0
    return {"micro_spread": spread, "micro_imbalance": imbalance, "micro_mid": mid}


class MarketStateUpdater:
    """
    Subscribes to MARKET_DATA and keeps OMS market_state cache fresh for SOR decisions.

    Convention:
    - `event.data` may include: bid, ask, bid_size, ask_size, top_depth, spread_pct, venue
    - venue is read from `event.data["venue"]` else defaults to `default_venue`.
    """

    def __init__(self, oms: UnifiedOMS, default_venue: str = "default") -> None:
        self.oms = oms
        self.default_venue = default_venue
        self._orderbooks: dict[tuple[str, str], OrderbookEngine] = {}

    async def on_market_data(self, event: MarketDataEvent) -> None:
        data = event.data or {}
        venue = str(data.get("venue") or self.default_venue)

        state: dict[str, Any] = {}
        for k in (
            "bid",
            "ask",
            "bid_size",
            "ask_size",
            "top_depth",
            "spread_pct",
            "trade_price",
            "trade_qty",
            "trade_side",
            "trade_ts",
        ):
            if k in data and data[k] is not None:
                state[k] = data[k]

        bid = state.get("bid")
        ask = state.get("ask")
        if bid is not None and ask is not None and float(ask) > 0:
            mid = (float(bid) + float(ask)) / 2.0
            spread_pct = (float(ask) - float(bid)) / float(ask)
            state.setdefault("mid", mid)
            state.setdefault("spread_pct", spread_pct)

        # Enrich with microstructure features using Rust core if available; fallback to Python.
        if bid is not None and ask is not None:
            key = (venue, event.symbol)
            try:
                if OrderbookEngine is not None:
                    ob = self._orderbooks.get(key)
                    if ob is None:
                        ob = OrderbookEngine(8)
                        self._orderbooks[key] = ob
                    # Update top-of-book levels; use price as key and size as qty.
                    ob.apply_l2_update("BUY", float(bid), float(state.get("bid_size", 0.0) or 0.0))
                    ob.apply_l2_update("SELL", float(ask), float(state.get("ask_size", 0.0) or 0.0))
                    spread, imbalance, mid = ob.compute_microstructure_features()
                    state["micro_spread"] = spread
                    state["micro_imbalance"] = imbalance
                    state["micro_mid"] = mid
                else:
                    state.update(_compute_micro_features_py(state))
            except Exception:
                state.update(_compute_micro_features_py(state))

        if state:
            self.oms.update_market_state(venue, event.symbol, state)
