import json
import logging
from datetime import datetime
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

    def load_log(self, log_path: str = "data/events/event_log.jsonl") -> int:
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
        
        # Reset local state before replay
        # In a real system, we might clone the current one or use a clean instance.
        
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
        """Feeds a single event into the state store logic."""
        etype = event.get("type")
        
        if etype == "FILL":
            # Reconstruction logic for fills (updates positions)
            symbol = event["symbol"]
            qty = event["quantity"]
            price = event["price"]
            side = event["side"]
            
            # Use current state_store getters/setters
            pos = await self.state_store.get_position(symbol)
            qty_dec = float(qty) if side == "BUY" else -float(qty)
            
            if pos:
                # Basic average price reconstruction
                new_qty = float(pos.quantity) + qty_dec
                # Simplified cost basis update for replay
                # Replace with Decimal if fidelity is required
                await self.state_store.set_position(Position(
                    symbol=symbol,
                    quantity=new_qty,
                    average_price=float(price) # Placeholder
                ))
            else:
                await self.state_store.set_position(Position(
                    symbol=symbol,
                    quantity=qty_dec,
                    average_price=float(price)
                ))

        elif etype == "ORDER":
            # Reconstruction logic for orders
            await self.state_store.set_order(Order(
                order_id=event["order_id"],
                symbol=event["symbol"],
                side=event["side"],
                order_type=event["order_type"],
                quantity=event["quantity"],
                status="PENDING" # Replay starts in pending
            ))
            
        elif etype == "RISK":
            # Reconstruct risk state
            # If the log contains metrics, we apply them to state_store
            metrics = event.get("metrics", {})
            # In a real system, we'd apply to self.state_store.set_risk_state()
            pass
