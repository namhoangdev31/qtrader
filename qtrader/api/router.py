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

from qtrader.analytics.session_analyzer import SessionAnalyzer
from qtrader.api.dependencies import get_system
from qtrader.api.schemas import (
    OrderRequest,
    PositionRow,
    SimulationConfig,
    StatusResponse,
)
from qtrader.core.events import EventType, OrderEvent, OrderPayload
from qtrader.persistence.db_writer import TradeDBWriter
from qtrader.trading_system import TradingSystem  # noqa: TC001

logger = logging.getLogger("qtrader.api.router")

router = APIRouter(prefix="/api/v1", tags=["Trading"])
ws_router = APIRouter(tags=["WebSockets"])
health_router = APIRouter(tags=["Internal"])
sim_router = APIRouter(prefix="/api/v1/sim", tags=["Simulation"])
session_router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])

_simulation_engine: Any | None = None
_simulation_task: asyncio.Task | None = None
_is_subscribed: bool = False


def get_sim_engine() -> Any:
    global _simulation_engine
    if _simulation_engine is None:
        from qtrader.execution.paper_engine import PaperTradingEngine

        _simulation_engine = PaperTradingEngine(
            starting_capital=1000.0,
            fee_rate=0.04,
            sl_pct=0.02,
            tp_pct=0.03,
            tick_interval=1.0,  # Baseline stabilized to 1.0s to reduce noise
            base_price=50000.0,
        )
    return _simulation_engine


async def start_simulation(sys: TradingSystem | None = None) -> None:
    global _simulation_task, _is_subscribed
    engine = get_sim_engine()

    # Sync base price and subscribe to real-time updates from EventBus
    if sys:
        try:
            # 1. Initial manual sync
            symbol = "BTC-USD"
            quote = sys.broker._quotes.get(symbol, {})
            real_price = float(quote.get("price") or 0.0)
            if real_price > 0:
                engine.update_base_price(real_price, force_current=True)
                logger.info(f"[SIM] Synced simulation to real price: {real_price:.2f}")

            # 2. Subscribe for continuous real-time updates
            if not _is_subscribed:
                sys.event_bus.subscribe(EventType.MARKET_DATA, engine.handle_market_event)
                _is_subscribed = True
                logger.info("[SIM] Subscribed PaperTradingEngine to live MARKET_DATA via EventBus")

        except Exception as e:
            logger.warning(f"[SIM] Failed to setup real-time sync: {e}")

    if _simulation_task is None or _simulation_task.done():
        _simulation_task = asyncio.create_task(engine.run_continuous())


async def stop_simulation() -> None:
    global _simulation_task
    if _simulation_task and not _simulation_task.done():
        _simulation_task.cancel()
        try:
            await _simulation_task
        except asyncio.CancelledError:
            pass
        _simulation_task = None


@sim_router.get("/status")
async def get_sim_status() -> dict[str, Any]:
    engine = get_sim_engine()
    return {
        "running": engine._running,
        "equity": round(engine.equity, 2),
        "cash": round(engine.cash, 2),
        "realized_pnl": round(engine.realized_pnl, 2),
        "total_commissions": round(engine.total_commissions, 4),
        "open_positions": len(engine._open_positions),
        "total_trades": len(engine._trade_history),
    }


@sim_router.get("/snapshot")
async def get_sim_snapshot() -> dict[str, Any]:
    engine = get_sim_engine()
    return engine._build_snapshot()


@sim_router.get("/trades")
async def get_trade_history(limit: int = 100) -> list[dict[str, Any]]:
    engine = get_sim_engine()
    return engine.trade_history[-limit:]


@sim_router.post("/start")
async def start_sim_endpoint(sys: TradingSystem = Depends(get_system)) -> dict[str, str]:
    await start_simulation(sys)
    return {"status": "started"}


@sim_router.post("/stop")
async def stop_sim_endpoint() -> dict[str, str]:
    await stop_simulation()
    return {"status": "stopped"}


@sim_router.post("/reset")
async def reset_sim_endpoint() -> dict[str, str]:
    await stop_simulation()
    engine = get_sim_engine()
    engine.reset()
    return {"status": "reset"}


@sim_router.post("/config")
async def update_sim_config(cfg: SimulationConfig) -> dict[str, Any]:
    global _simulation_task
    await stop_simulation()
    global _simulation_engine
    from qtrader.execution.paper_engine import PaperTradingEngine

    _simulation_engine = PaperTradingEngine(
        starting_capital=cfg.initial_balance,
        fee_rate=0.04,
        sl_pct=cfg.sl_pct,
        tp_pct=cfg.tp_pct,
        tick_interval=cfg.tick_interval,
        base_price=cfg.base_price,
    )
    return {"status": "configured", "message": "Simulation restarted with new config"}


# --- Session Management ---

@session_router.post("/start")
async def start_session(
    metadata: dict[str, Any] | None = None, sys: TradingSystem = Depends(get_system)
) -> dict[str, Any]:
    writer = TradeDBWriter()
    active = await writer.get_active_session()
    if active:
        return {
            "status": "error",
            "message": "A session is already active",
            "session_id": active["session_id"],
        }

    # Capture initial capital from broker/engine
    balance = await sys.broker.get_paper_balance()
    initial_equity = Decimal(str(balance["equity"]))

    session_id = await writer.start_session(initial_equity, metadata)
    sys.active_session_id = session_id

    return {"status": "started", "session_id": session_id, "initial_capital": float(initial_equity)}


@session_router.post("/stop")
async def stop_session(
    session_id: str | None = None, sys: TradingSystem = Depends(get_system)
) -> dict[str, Any]:
    writer = TradeDBWriter()
    analyzer = SessionAnalyzer()

    active = await writer.get_active_session()
    if not active:
        raise HTTPException(status_code=404, detail="No active session found")

    s_id = session_id or active["session_id"]
    start_time = active["start_time"].isoformat()

    # Capture final capital
    balance = await sys.broker.get_paper_balance()
    final_equity = Decimal(str(balance["equity"]))

    # Generate forensic report
    report = await analyzer.analyze_session(s_id, start_time)

    # Persist and close
    await writer.stop_session(s_id, final_equity, report)

    # Clear active session in system
    if sys.active_session_id == s_id:
        sys.active_session_id = None

    return {"status": "completed", "report": report, "final_capital": float(final_equity)}


@session_router.get("/active")
async def get_active_session() -> dict[str, Any]:
    writer = TradeDBWriter()
    active = await writer.get_active_session()
    return {"active": active is not None, "session": active}


@session_router.get("/history")
async def get_session_history(limit: int = 10) -> list[dict[str, Any]]:
    writer = TradeDBWriter()
    return await writer.get_session_history(limit)


@session_router.get("/{session_id}/report")
async def get_session_report(session_id: str) -> dict[str, Any]:
    writer = TradeDBWriter()
    session = await writer.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "report": session.get("summary")}


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
    """Get active positions from the system (Redundant, use WebSocket)."""
    # Fetch from sys state store which is synced with Redis
    positions = await sys.state_store.get_positions()

    rows = []
    for sym, pos in positions.items():
        q = float(pos.quantity)
        if q != 0:
            rows.append(
                {
                    "symbol": sym,
                    "quantity": q,
                    "average_price": float(pos.average_price),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                    "unrealized_pnl_pct": 0.0,  # Will improve later
                }
            )
    return rows


@router.post("/order")
async def place_order(
    req: OrderRequest,
    sys: TradingSystem = Depends(get_system),  # noqa: B008
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
    start = now - (100 * 60)  # 100 minutes ago

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
        o = c + random.uniform(-volatility, volatility)  # noqa: S311
        h = max(o, c) + random.uniform(0, volatility / 2)  # noqa: S311
        px_l = min(o, c) - random.uniform(0, volatility / 2)  # noqa: S311
        v = random.uniform(10, 100)  # noqa: S311

        candles.append(
            {
                "time": t,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(px_l, 2),
                "close": round(c, 2),
                "volume": round(v, 2),
            }
        )
        temp_price = o  # Next candle's close is this one's open (walking backwards)

    return sorted(candles, key=lambda x: x["time"])


@ws_router.websocket("/ws/trading")
async def trading_updates(websocket: WebSocket) -> None:
    """Unified WebSocket for all trading updates: Positions, Logs, PnL."""
    logger.info("[WS] New WebSocket connection attempt on /ws/trading")
    try:
        await websocket.accept()
        logger.info("[WS] WebSocket connection accepted on /ws/trading")
    except Exception as e:
        logger.error(f"[WS] Failed to accept WebSocket connection: {e}", exc_info=True)
        return

    try:
        sys = get_system()
        logger.info("[WS] TradingSystem instance acquired")
    except Exception as e:
        logger.error(f"[WS] Failed to get TradingSystem: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": f"System unavailable: {e}"})
        except Exception:
            pass
        return

    # Helper to build current state snapshot
    async def get_snapshot(msg_type: str = "incremental_update") -> dict[str, Any]:
        try:
            positions = await sys.state_store.get_positions()
            pos_rows = [
                {
                    "symbol": sym,
                    "quantity": float(pos.quantity),
                    "average_price": float(pos.average_price),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                    "unrealized_pnl_pct": 0.0,
                }
                for sym, pos in positions.items()
            ]
        except Exception as e:
            logger.error(f"[WS] Failed to get positions: {e}", exc_info=True)
            pos_rows = []

        try:
            balance = await sys.broker.get_paper_balance()
        except Exception as e:
            logger.error(f"[WS] Failed to get paper balance: {e}", exc_info=True)
            balance = {"equity": 0.0, "realized_pnl": 0.0, "total_commissions": 0.0}

        try:
            status = sys.get_status()
        except Exception as e:
            logger.error(f"[WS] Failed to get system status: {e}", exc_info=True)
            status = {"running": False, "mode": "unknown", "error": str(e)}

        update = {
            "type": msg_type,
            "timestamp": datetime.now().isoformat(),
            "positions": pos_rows,
            "status": status,
            "recent_logs": [],
            # ATOMIC FLATTENING: Match frontend SimSnapshot expected top-level fields
            "equity": balance["equity"],
            "cash": balance["cash"],
            "realized_pnl": balance["realized_pnl"],
            "total_commissions": balance["total_commissions"],
            "current_price": sys.last_price if hasattr(sys, "last_price") else 0.0,
            "live_trace": {
                "module_traces": getattr(sys, "_last_module_traces", {})
            },
            "adaptive": getattr(sys.broker.paper_account, "adaptive", {}) if hasattr(sys.broker, "paper_account") else {}
        }
        return update

    # Send initial snapshot
    try:
        snapshot = await get_snapshot("initial_snapshot")
        await websocket.send_json(snapshot)
        logger.info(
            f"[WS] Initial snapshot sent | equity={snapshot['pnl_summary']['total_equity']} | positions={len(snapshot['positions'])}"
        )
    except Exception as e:
        logger.error(f"[WS] Failed to send initial snapshot: {e}", exc_info=True)

    # Subscribe to PUSH updates
    queue: asyncio.Queue[bool] = asyncio.Queue()
    update_count = 0

    async def update_handler(event: Any) -> None:
        try:
            await queue.put(True)
        except Exception as e:
            logger.error(f"[WS] Failed to queue update: {e}", exc_info=True)

    try:
        sys.event_bus.subscribe(EventType.FILL, update_handler)
        sys.event_bus.subscribe(EventType.SYSTEM, update_handler)
        sys.event_bus.subscribe(EventType.MARKET, update_handler) # HEARTBEAT: Pulse on every tick
        logger.info("[WS] Subscribed to FILL, SYSTEM, and MARKET events for real-time pulses")
    except Exception as e:
        logger.error(f"[WS] Failed to subscribe to events: {e}", exc_info=True)

    try:
        while True:
            await queue.get()
            update_count += 1
            try:
                snapshot = await get_snapshot()
                await websocket.send_json(snapshot)
            except Exception as e:
                logger.error(f"[WS] Failed to send update #{update_count}: {e}", exc_info=True)
                break

    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected from /ws/trading after {update_count} updates")
    except Exception as e:
        logger.error(f"[WS] Unexpected error in WebSocket loop: {e}", exc_info=True)
        raise
    finally:
        try:
            sys.event_bus.unsubscribe(EventType.FILL, update_handler)
            sys.event_bus.unsubscribe(EventType.SYSTEM, update_handler)
            logger.info("[WS] Unsubscribed from event bus for /ws/trading")
        except Exception as e:
            logger.error(f"[WS] Failed to unsubscribe: {e}", exc_info=True)


@ws_router.websocket("/ws/simulation")
async def simulation_updates(websocket: WebSocket) -> None:
    """WebSocket for real-time simulation updates."""
    try:
        await websocket.accept()
    except Exception as e:
        logger.error(f"[WS/SIM] Failed to accept: {e}", exc_info=True)
        return

    engine = get_sim_engine()
    update_queue: asyncio.Queue[bool] = asyncio.Queue()

    def on_sim_update(data: dict[str, Any]) -> None:
        try:
            update_queue.put_nowait(True)
        except Exception:
            pass

    engine.set_update_handler(on_sim_update)

    try:
        snapshot = engine._build_snapshot()
        await websocket.send_json(snapshot)
    except Exception:
        pass

    update_count = 0
    try:
        while True:
            await update_queue.get()
            update_count += 1
            try:
                snapshot = engine._build_snapshot()
                await websocket.send_json(snapshot)
            except Exception as e:
                logger.error(f"[WS/SIM] Failed to send update #{update_count}: {e}")
                break
    except WebSocketDisconnect:
        logger.info(f"[WS/SIM] Client disconnected after {update_count} updates")
    except Exception as e:
        logger.error(f"[WS/SIM] Unexpected error: {e}", exc_info=True)
