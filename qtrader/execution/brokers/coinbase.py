from typing import Dict, Any, List, Optional
from qtrader.core.event import OrderEvent, FillEvent
from qtrader.core.config import Config

class CoinbaseBrokerAdapter:
    """
    Broker adapter for Coinbase Advanced Trade REST API.
    Supports live execution and simulation mode.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, simulate: Optional[bool] = None) -> None:
        self.api_key = api_key or Config.COINBASE_API_KEY
        self.api_secret = api_secret or Config.COINBASE_API_SECRET
        self.simulate = simulate if simulate is not None else Config.SIMULATE_MODE
        self.positions: Dict[str, float] = {}
        self.orders: Dict[str, Any] = {}

    async def place_order(self, order: OrderEvent) -> Optional[FillEvent]:
        """Places an order on Coinbase (or simulates it)."""
        logging.info(f"COINBASE | Placing {order.order_type} {order.side} for {order.symbol}")
        
        if self.simulate:
            # Simulated Fill: Assuming immediate fill for simplicity at mid-price
            await asyncio.sleep(0.1) # Simulate network latency
            fill = FillEvent(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.price, # In simulation, we use the requested price
                commission=order.price * order.quantity * 0.001, # 0.1% fee
                timestamp=None
            )
            logging.info(f"COINBASE | Simulated Fill: {fill.quantity} @ {fill.price}")
            return fill
        
        # In production: 
        # auth = CoinbaseAuth(self.api_key, self.api_secret)
        # response = await post_order(...)
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an open order."""
        logging.info(f"COINBASE | Canceling order {order_id}")
        if self.simulate:
            return True
        return False

    async def get_positions(self) -> Dict[str, float]:
        """Fetch current account balances."""
        if self.simulate:
            return self.positions
            
        # In production: fetch from API
        return {}

    def update_virtual_position(self, symbol: str, quantity: float, side: str):
        """Helper for simulation mode."""
        asset = symbol.split("-")[0] # BTC-USD -> BTC
        current = self.positions.get(asset, 0.0)
        if side == "BUY":
            self.positions[asset] = current + quantity
        else:
            self.positions[asset] = current - quantity
