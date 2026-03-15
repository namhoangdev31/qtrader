import logging
import uuid
from dataclasses import dataclass
from typing import Any

from qtrader.core.event import FillEvent, OrderEvent
from qtrader.output.execution.oms import PositionManager

_LOG = logging.getLogger("qtrader.paper")

@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    slippage_bps: float
    venue: str

class PaperTradingEngine:
    """
    Executes simulated orders against real Coinbase market data.
    Tracks P&L and computes realistic slippage via Kyle's Lambda.
    """
    def __init__(self, starting_capital: float = 100000.0) -> None:
        self.starting_capital = starting_capital
        self.position_manager = PositionManager()
        self.closed_trades: list[TradeRecord] = []
        
        # Simple tracking of average entry to compute closed trade P&L accurately
        # dict[symbol, tuple(qty, avg_price)]
        self._open_positions: dict[str, tuple[float, float]] = {}

    def _kyle_lambda(self, order_qty: float, top_depth: float) -> float:
        """
        Estimate price impact (slippage) based on order size vs top-of-book depth.
        If top_depth is 0 or very small, assume high slippage.
        """
        if top_depth <= 0:
            return 0.0010  # 10 bps default penalty for missing depth
        
        # Base slippage of 0.5 bps + impact
        ratio = order_qty / top_depth
        impact = 0.00005 + (0.0002 * ratio)
        
        # Max slippage capped at 5% for safety in simulation
        return min(impact, 0.05)

    def simulate_fill(self, order: OrderEvent, market_state: dict[str, Any]) -> FillEvent:
        """
        Process the order against the current market state and generate a fill.
        """
        bid = float(market_state.get("bid", 0.0))
        ask = float(market_state.get("ask", 0.0))
        top_depth = float(market_state.get("top_depth", 0.0))
        
        if ask <= 0 or bid <= 0:
            _LOG.warning(f"Invalid market state for {order.symbol}: bid={bid}, ask={ask}. Cannot fill.")
            # Fallback to order price if provided
            if order.price:
                price = order.price
            else:
                raise ValueError(f"No valid price available to fill {order.symbol}")
        else:
            mid = (bid + ask) / 2.0
            slippage = self._kyle_lambda(order.quantity, top_depth)
            
            # Assume we cross the spread
            if order.side.upper() == "BUY":
                price = ask * (1 + slippage)
            else:
                price = bid * (1 - slippage)

        # Apply a flat commission in simulation (e.g. 0.05%)
        commission = price * order.quantity * 0.0005

        fill = FillEvent(
            symbol=order.symbol,
            quantity=order.quantity,
            price=price,
            commission=commission,
            side=order.side,
            order_id=order.order_id or str(uuid.uuid4()),
            fill_id=str(uuid.uuid4()),
        )
        
        # Track the trade for EV calculation
        self._record_trade(fill, market_state.get("venue", "SIMULATED_COINBASE"))
        
        # Update OM position manager
        self.position_manager.on_fill(fill, float(mid) if (bid > 0 and ask > 0) else price)
        
        return fill

    def _record_trade(self, fill: FillEvent, venue: str) -> None:
        """Track entry and exit for closed P&L records."""
        sym = fill.symbol
        side = fill.side.upper()
        qty = fill.quantity
        price = fill.price
        
        curr_qty, curr_price = self._open_positions.get(sym, (0.0, 0.0))
        
        if curr_qty == 0:
            # Opening new position
            sign = 1 if side == "BUY" else -1
            self._open_positions[sym] = (qty * sign, price)
        elif (curr_qty > 0 and side == "BUY") or (curr_qty < 0 and side == "SELL"):
            # Adding to position
            sign = 1 if side == "BUY" else -1
            new_qty = abs(curr_qty) + qty
            new_price = ((abs(curr_qty) * curr_price) + (qty * price)) / new_qty
            self._open_positions[sym] = (new_qty * sign, new_price)
        else:
            # Closing position (partial or full)
            closing_qty = min(abs(curr_qty), qty)
            sign = 1 if curr_qty > 0 else -1
            
            # Calculate PnL on the closed portion
            if curr_qty > 0: # Long position closed by SELL
                pnl = (price - curr_price) * closing_qty
                pnl_pct = (price - curr_price) / curr_price
            else: # Short position closed by BUY
                pnl = (curr_price - price) * closing_qty
                pnl_pct = (curr_price - price) / curr_price
                
            # Assume mid price was curr_price, slippage proxy
            slippage_bps = abs(price - curr_price) / curr_price * 10000.0 if curr_price > 0 else 0
            
            record = TradeRecord(
                symbol=sym,
                side=side,
                entry_price=curr_price,
                exit_price=price,
                qty=closing_qty,
                pnl=pnl - fill.commission, # Net PnL
                pnl_pct=pnl_pct,
                slippage_bps=slippage_bps,
                venue=venue
            )
            self.closed_trades.append(record)
            
            # Update remaining
            rem_qty = abs(curr_qty) - closing_qty
            if rem_qty <= 1e-8:
                self._open_positions.pop(sym, None)
            else:
                self._open_positions[sym] = (rem_qty * sign, curr_price)
            
            # If the closing order was larger than the open position, flipped direction
            if qty > abs(curr_qty):
                flipped_qty = qty - abs(curr_qty)
                flipped_sign = 1 if side == "BUY" else -1
                self._open_positions[sym] = (flipped_qty * flipped_sign, price)
