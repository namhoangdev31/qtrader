import logging
import uuid
from dataclasses import dataclass
from typing import Any

from qtrader.core.event import FillEvent, OrderEvent
from qtrader.oms.order_management_system import PositionManager

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
    def __init__(self, starting_capital: float = 100000.0, fee_rate: float = 0.0004) -> None:
        self.starting_capital = starting_capital
        self.fee_rate = fee_rate
        self.position_manager = PositionManager()
        self.closed_trades: list[TradeRecord] = []
        
        # position tracking: dict[symbol, tuple(qty, avg_price, avg_commission_per_unit)]
        self._open_positions: dict[str, tuple[float, float, float]] = {}

    def _kyle_lambda(self, order_qty: float, top_depth: float) -> float:
        """
        Estimate price impact (slippage) based on order size vs top-of-book depth.
        Using a more conservative 10 bps max cap for liquid crypto books.
        """
        if top_depth <= 0:
            return 0.0005  # 5 bps default penalty
        
        # Base slippage of 0.2 bps + impact
        ratio = order_qty / top_depth
        impact = 0.00002 + (0.0001 * ratio)
        
        # Max slippage capped at 10 bps (0.1%) for institutional realism
        return min(impact, 0.0010)

    def simulate_fill(self, order: OrderEvent, market_state: dict[str, Any]) -> FillEvent:
        """
        Process the order against the current market state and generate a fill.
        """
        bid = float(market_state.get("bid", 0.0))
        ask = float(market_state.get("ask", 0.0))
        top_depth = float(market_state.get("top_depth", 0.0))
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0
        
        if ask <= 0 or bid <= 0:
            _LOG.warning(f"Invalid market state for {order.symbol}: bid={bid}, ask={ask}. Cannot fill.")
            if order.price:
                price = order.price
            else:
                raise ValueError(f"No valid price available to fill {order.symbol}")
        else:
            slippage = self._kyle_lambda(order.quantity, top_depth)
            
            # Cross the spread + price impact
            if order.side.upper() == "BUY":
                price = ask * (1 + slippage)
            else:
                price = bid * (1 - slippage)

        # Apply a flat commission
        commission = price * order.quantity * self.fee_rate

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
        self._record_trade(fill, market_state.get("venue", "SIMULATED_COINBASE"), mid)
        
        # Update OM position manager
        self.position_manager.on_fill(fill, mid if mid > 0 else price)
        
        return fill

    def _record_trade(self, fill: FillEvent, venue: str, mid_price: float) -> None:
        """Track entry and exit for closed P&L records with accurate fee subtraction."""
        sym = fill.symbol
        side = fill.side.upper()
        qty = fill.quantity
        price = fill.price
        comm = fill.commission
        comm_per_unit = comm / qty if qty > 0 else 0.0
        
        # mid_price is used to calculate TRUE slippage (impact + spread)
        # falling back to price if mid is unavailable (though it shouldn't be)
        ref_mid = mid_price if mid_price > 0 else price
        
        curr_qty, curr_price, curr_comm_per_unit = self._open_positions.get(sym, (0.0, 0.0, 0.0))
        
        if curr_qty == 0:
            # New position
            sign = 1 if side == "BUY" else -1
            self._open_positions[sym] = (qty * sign, price, comm_per_unit)
        elif (curr_qty > 0 and side == "BUY") or (curr_qty < 0 and side == "SELL"):
            # Increasing position
            sign = 1 if side == "BUY" else -1
            total_qty = abs(curr_qty) + qty
            avg_price = ((abs(curr_qty) * curr_price) + (qty * price)) / total_qty
            avg_comm = ((abs(curr_qty) * curr_comm_per_unit) + comm) / total_qty
            self._open_positions[sym] = (total_qty * sign, avg_price, avg_comm)
        else:
            # Closing position
            closing_qty = min(abs(curr_qty), qty)
            
            # Gross directional PnL
            if curr_qty > 0: # Long closed by SELL
                gross_pnl = (price - curr_price) * closing_qty
                pnl_pct = (price - curr_price) / curr_price
            else: # Short closed by BUY
                gross_pnl = (curr_price - price) * closing_qty
                pnl_pct = (curr_price - price) / curr_price
            
            # Net PnL = gross - (entry fees pro-rata) - (exit fees pro-rata)
            exit_comm_share = (comm / qty) * closing_qty
            entry_comm_share = curr_comm_per_unit * closing_qty
            net_pnl = gross_pnl - entry_comm_share - exit_comm_share
            
            # slippage relative to MID price (standard institutional metric)
            slippage_bps = (abs(price - ref_mid) / ref_mid) * 10000.0 if ref_mid > 0 else 0
            
            record = TradeRecord(
                symbol=sym,
                side=side,
                entry_price=curr_price,
                exit_price=price,
                qty=closing_qty,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                slippage_bps=slippage_bps,
                venue=venue
            )
            self.closed_trades.append(record)
            
            # Update remaining
            rem_qty = abs(curr_qty) - closing_qty
            sign = 1 if curr_qty > 0 else -1
            
            if rem_qty < 1e-8:
                self._open_positions.pop(sym, None)
            else:
                self._open_positions[sym] = (rem_qty * sign, curr_price, curr_comm_per_unit)
            
            # If flip
            if qty > closing_qty:
                flipped_qty = qty - closing_qty
                flipped_sign = 1 if side == "BUY" else -1
                # Commission for the flipped portion is pro-rata of current fill
                self._open_positions[sym] = (flipped_qty * flipped_sign, price, comm_per_unit)
