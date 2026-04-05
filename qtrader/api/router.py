"""FastAPI Routes for QTrader."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from qtrader.api.dependencies import get_system
from qtrader.api.schemas import OrderRequest, PositionRow, StatusResponse
from qtrader.core.events import EventType, MarketEvent, MarketPayload, OrderEvent, OrderPayload
from qtrader.trading_system import TradingSystem  # noqa: TC001

logger = logging.getLogger("qtrader.api.router")

router = APIRouter(prefix="/api/v1", tags=["Trading"])
ws_router = APIRouter(tags=["WebSockets"])
health_router = APIRouter(tags=["Internal"])

@health_router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for Docker."""
    return {"status": "healthy", "service": "API_DASHBOARD"}


@router.get("/status", response_model=StatusResponse)
async def get_status(sys: TradingSystem = Depends(get_system)) -> dict[str, Any]:  # noqa: B008
    """Get overall system status."""
    return sys.get_status()


@router.get("/positions", response_model=list[PositionRow])
async def get_positions(
    sys: TradingSystem = Depends(get_system),  # noqa: B008
) -> list[dict[str, Any]]:
    """Get active positions from the system."""
    # Since StateStore doesn't record PnL directly without fills logic,
    # we simulate fetching current positions.
    # In a real app we'd fetch directly from state_store or broker.
    
    # Fetch directly from paper broker balance
    balance = await sys.broker.get_balance()
    positions = balance.get("positions", {})
    
    rows = []
    for sym, qty in positions.items():
        q = float(qty)
        if q != 0:
            # Try to get current price for PnL calculation
            # Symbols in balance might be just 'BTC', while quotes are 'BTC-USD'
            quote_sym = f"{sym}-USD" if "-" not in sym else sym
            quote = sys.broker._quotes.get(quote_sym, {})
            current_price = float((quote.get("bid", 0) + quote.get("ask", 0)) / 2)
            
            # For paper trading, we assume an average cost of 0 if not tracked,
            # but let's use a dummy avg price for visualization
            avg_price = 60000.0 # placeholder
            upnl = (current_price - avg_price) * q if current_price > 0 else 0.0
            
            rows.append({
                "symbol": sym,
                "quantity": q,
                "average_price": avg_price,
                "unrealized_pnl": round(upnl, 2),
                "unrealized_pnl_pct": round((upnl / (avg_price * q)) * 100, 2) if q != 0 and avg_price > 0 else 0.0,
            })
    return rows


@router.post("/order")
async def place_order(
    req: OrderRequest, sys: TradingSystem = Depends(get_system)  # noqa: B008
) -> dict[str, Any]:
    """Submit a manual paper trade."""
    
    # Create order event
    import uuid
    order = OrderEvent(
        source="api_dashboard",
        payload=OrderPayload(
            order_id=str(uuid.uuid4()),
            symbol=req.symbol,
            action=req.side,
            quantity=Decimal(str(req.quantity)),
            price=None,
            order_type=req.order_type,
        ),
    )
    
    try:
        order_id = await sys.broker.submit_order(order)
        return {
            "status": "success",
            "order_id": order_id,
            "message": f"Placed {req.side} {req.quantity} {req.symbol}",
        }
    except Exception as e:
        logger.error(f"Failed to place manual order: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
        

@router.get("/history")
async def get_market_history(
    symbol: str = "BTC-USD", sys: TradingSystem = Depends(get_system)
) -> list[dict[str, Any]]:
    """Return simulated historical candles for TradingView."""
    now = int(time.time())
    start = now - (100 * 60) # 100 minutes ago
    
    # Get current real price from broker as anchor
    quote = sys.broker._quotes.get(symbol, {})
    current_price = float(quote.get("price") or 50000.0)
    
    # Generate 100 candles walking backwards from current price
    candles = []
    temp_price = current_price
    
    for t in range(now - 60, start - 60, -60):
        # Inverse random walk to generate historical data
        # Scaled down to +/- 0.1 USD per minute to fit user's request
        volatility = 0.1 
        c = temp_price
        o = c + random.uniform(-volatility, volatility) # noqa: S311
        h = max(o, c) + random.uniform(0, volatility / 2) # noqa: S311
        px_l = min(o, c) - random.uniform(0, volatility / 2) # noqa: S311
        v = random.uniform(10, 100) # noqa: S311
        
        candles.append({
            "time": t,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(px_l, 2),
            "close": round(c, 2),
            "volume": round(v, 2),
        })
        temp_price = o # Next candle's close is this one's open (walking backwards)
        
    return sorted(candles, key=lambda x: x["time"])


@ws_router.websocket("/ws/market/{symbol}")
async def market_stream(websocket: WebSocket, symbol: str) -> None:
    """Stream live market data from the active trading system."""
    await websocket.accept()
    logger.info(f"WebSocket client connected for {symbol}")
    
    sys = get_system()
    
    # Push-based Subscription
    queue: asyncio.Queue[MarketPayload] = asyncio.Queue()
    
    # Callback handler for EventBus
    async def market_handler(event: Any) -> None:
        if isinstance(event, MarketEvent) and event.symbol == symbol:
            await queue.put(event.payload)
            
    # Subscribe to EventBus
    sys.event_bus.subscribe(EventType.MARKET_DATA, market_handler)
    
    try:
        # Initial push of last known price if available
        quote = sys.broker._quotes.get(symbol, {})
        last_price = float(quote.get("price", 0))
        if last_price > 0:
            await websocket.send_json({
                "time": int(time.time()),
                "price": last_price
            })

        while True:
            # Wait for next event from Queue (PUSH!)
            payload = await queue.get()
            
            # Send candlestick-friendly update (Unix timestamp, price)
            # Priority: Mid-price (bid/ask) > Price field > data.get('price')
            if payload.bid > 0 and payload.ask > 0:
                price = float((payload.bid + payload.ask) / 2)
            elif payload.data and "price" in payload.data:
                price = float(payload.data["price"])
            else:
                price = float(payload.bid)
            
            msg = {
                "time": int(time.time()), 
                "price": price
            }
            await websocket.send_json(msg)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from {symbol}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        sys.event_bus.unsubscribe(EventType.MARKET_DATA, market_handler)
