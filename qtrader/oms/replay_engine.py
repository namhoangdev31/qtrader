import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, List

from qtrader.core.state_store import StateStore, Position, Order
from qtrader.core.event import EventType

_LOG = logging.getLogger("qtrader.oms.replay_engine")


class ReplayEngine:
    """Replays system events to reconstruct authoritative state.
    
    Deterministic Replay: State(t) = Σ Events[0 → t]
    """

    def __init__(self, state_store: StateStore | None = None) -> None:
        self.state_store = state_store or StateStore()
        self.events: List[dict[str, Any]] = []

    def load_log(self, log_path: str = "data/events/order_event_log.jsonl") -> int:
        """Load history from file into memory for faster re-processing."""
        log_file = Path(log_path)
        if not log_file.exists():
            _LOG.warning(f"REPLAY_ENGINE | Log file {log_path} not found")
            return 0

        self.events = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.events.append(json.loads(line))
        
        _LOG.info(f"REPLAY_ENGINE | Loaded {len(self.events)} events from {log_path}")
        return len(self.events)

    async def replay_upto(self, target_time: datetime) -> None:
        """Reconstruct state from start up to T."""
        _LOG.info(f"REPLAY_ENGINE | Replaying up to {target_time.isoformat()}")
        
        # Iteratively process events
        for event in self.events:
            ts_str = event.get("timestamp")
            if not ts_str:
                continue
                
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts > target_time:
                break
            
            await self._process_single_event(event)
            
        _LOG.info("REPLAY_ENGINE | Replay complete.")

    async def _process_single_event(self, event: dict[str, Any]) -> None:
        """Feeds a single event into the state store logic using the authoritative FSM."""
        etype_val = event.get("type")
        
        # Standardizing EventType lookup
        try:
            # Handle if etype_val is a string (e.g. from JSON value) or int
            if isinstance(etype_val, str):
                # Check for standardized event types
                if etype_val == "ORDER": etype = EventType.ORDER
                elif etype_val == "FILL": etype = EventType.FILL
                elif etype_val == "RISK": etype = EventType.RISK
                elif etype_val == "ORDER_CREATED": etype = EventType.ORDER_CREATED
                elif etype_val == "ORDER_FILLED": etype = EventType.ORDER_FILLED
                elif etype_val == "ORDER_REJECTED": etype = EventType.ORDER_REJECTED
                else: etype = None
            else:
                etype = None
        except Exception:
            etype = None

        if etype == EventType.FILL or etype == EventType.ORDER_FILLED:
            # Reconstruction logic for fills (updates positions)
            symbol = event["symbol"]
            qty = Decimal(str(event["quantity"]))
            price = Decimal(str(event["price"]))
            side = event["side"]
            
            p = await self.state_store.get_position(symbol)
            qty_delta = qty if side == "BUY" else -qty
            
            if p:
                new_qty = p.quantity + qty_delta
                # Simple average cost update during reconstruction
                new_cost = p.average_price
                if new_qty != 0 and qty_delta * p.quantity >= 0: # increasing position
                    new_cost = (p.quantity * p.average_price + qty * price) / new_qty
                
                await self.state_store.set_position(Position(
                    symbol=symbol,
                    quantity=new_qty,
                    average_price=new_cost
                ))
            else:
                await self.state_store.set_position(Position(
                    symbol=symbol,
                    quantity=qty_delta,
                    average_price=price
                ))

        elif etype == EventType.ORDER or etype == EventType.ORDER_CREATED:
            # Sync active orders in StateStore
            # Extract common order details
            o_data = event.get("order", event)
            await self.state_store.set_order(Order(
                order_id=o_data["order_id"],
                symbol=o_data["symbol"],
                side=o_data["side"],
                order_type=o_data["order_type"],
                quantity=Decimal(str(o_data["quantity"])),
                price=Decimal(str(o_data["price"])) if o_data.get("price") else None,
                status="ACK" if etype == EventType.ORDER_CREATED else "NEW"
            ))

        elif etype == EventType.ORDER_REJECTED:
            order_id = event["order_id"]
            # Clear or update order status in state store
            await self.state_store.remove_order(order_id)
            
        elif etype == EventType.RISK:
            # Reconstruct high-fidelity risk metrics
            pass
