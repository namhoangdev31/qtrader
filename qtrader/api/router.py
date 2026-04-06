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
from qtrader.core.dynamic_config import config_manager
from qtrader.core.events import EventType, MarketEvent, MarketPayload, OrderEvent, OrderPayload
from qtrader.trading_system import TradingSystem, TradingSystemConfig
from qtrader.persistence.db_writer import TradeDBWriter
from qtrader.ml.embedding_worker import embedding_manager

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
        # If a session is already active (e.g. started by Orchestrator), join it
        return {
            "status": "started",
            "message": "Connected to active session",
            "session_id": active["session_id"],
            "mode": active.get("mode", "UNKNOWN")
        }

    # ACTIVATE the entire trading system manually
    # This initializes Coinbase WebSockets, ML pipelines, and OMS
    await sys.start()
    
    return {
        "status": "started", 
        "session_id": sys.active_session_id, 
        "mode": "PAPER" if sys.config.simulate else "LIVE"
    }


@session_router.post("/stop")
async def stop_session(
    session_id: str | None = None, sys: TradingSystem = Depends(get_system)
) -> dict[str, Any]:
    # DEACTIVATE the entire system
    await sys.stop()

    writer = TradeDBWriter()
    analyzer = SessionAnalyzer()

    # Get the session we just stopped (or the last one)
    s_id = session_id or getattr(sys, "_last_session_id", None)
    if not s_id:
        # Fallback to DB
        active = await writer.get_active_session()
        if active: s_id = active["session_id"]

    if not s_id:
         raise HTTPException(status_code=404, detail="No session identifier found to analyze")

    # Generate forensic report from finalized DB data
    # Note: sys.stop() already closed the DB session recording.
    report = await analyzer.analyze_session(s_id, "2000-01-01") # Analyzer handles time windows via DB

    return {"status": "completed", "report": report}


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


@router.get("/forensic_notes")
async def get_forensic_notes(session_id: str | None = None) -> list[dict[str, Any]]:
    """Retrieve forensic notes for RAG/UI."""
    from qtrader.core.db import DBClient
    conn = await DBClient().get_connection()
    try:
        if session_id:
            rows = await conn.fetch("SELECT id, note_text, note_type, timestamp FROM forensic_notes WHERE session_id = $1 ORDER BY timestamp DESC", session_id)
        else:
            rows = await conn.fetch("SELECT id, note_text, note_type, timestamp FROM forensic_notes ORDER BY timestamp DESC LIMIT 100")
        return [{"id": str(r["id"]), "content": r["note_text"], "type": r["note_type"], "timestamp": r["timestamp"].isoformat()} for r in rows]
    except Exception as e:
        logger.error(f"[API] Failed to fetch notes: {e}")
        return []
    finally:
        await conn.close()


@router.post("/forensic_notes")
async def add_forensic_note(note: dict[str, Any], sys: TradingSystem = Depends(get_system)) -> dict[str, Any]:
    """Persist a forensic note and ENQUEUE for async embedding (Zero Latency)."""
    writer = TradeDBWriter()
    try:
        content = note.get("content", "")
        note_type = note.get("type", "OBSERVATION")
        session_id = sys.active_session_id
        
        # 1. Immediate Persistence (Sync-ish)
        note_id = await writer.write_forensic_note(
            content=content,
            note_type=note_type,
            session_id=session_id
        )
        
        # 2. Async Enqueue for Language Embedding (Non-blocking)
        embedding_manager.enqueue_note(note_id, content)
        
        # 3. If it's a high-priority forensic note, refresh the global sentiment context immediately
        if note_type in ["ALERT", "TRIAL"]:
            embedding_manager.refresh_sentiment(f"Manual Forensic Intervention: {content}")
        
        return {"status": "success", "note_id": note_id}
    except Exception as e:
        logger.error(f"[API] Failed to save note: {e}")
        raise HTTPException(status_code=400, detail=str(e))


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
    """Concentrated WebSocket for Portfolio: Positions, Cash, PnL."""
    await websocket.accept()
    sys = get_system()
    
    async def get_snapshot():
        balance = await sys.broker.get_paper_balance()
        positions = await sys.state_store.get_positions()
        return {
            "type": "portfolio_update",
            "timestamp": datetime.now().isoformat(),
            "equity": balance["equity"],
            "cash": balance["cash"],
            "realized_pnl": balance["realized_pnl"],
            "total_commissions": balance["total_commissions"],
            "positions": [
                {
                    "symbol": sym,
                    "quantity": float(pos.quantity),
                    "average_price": float(pos.average_price),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                }
                for sym, pos in positions.items() if pos.quantity != 0
            ]
        }

    await websocket.send_json(await get_snapshot())
    queue: asyncio.Queue[bool] = asyncio.Queue()
    
    async def handler(event): await queue.put(True)
    sys.event_bus.subscribe(EventType.FILL, handler)
    sys.event_bus.subscribe(EventType.SYSTEM, handler)

    try:
        while True:
            await queue.get()
            await websocket.send_json(await get_snapshot())
    except WebSocketDisconnect:
        pass
    finally:
        sys.event_bus.unsubscribe(EventType.FILL, handler)
        sys.event_bus.unsubscribe(EventType.SYSTEM, handler)


@ws_router.websocket("/ws/forensics")
async def forensics_updates(websocket: WebSocket) -> None:
    """High-fidelity WebSocket for Logic Matrix, AI Thinking, and Traces."""
    await websocket.accept()
    sys = get_system()
    engine = get_sim_engine()

    async def get_snapshot():
        # Build unified trace from system or simulation engine
        trace = getattr(sys, "_last_module_traces", {})
        if engine._running:
             trace = engine._last_trace.get("module_traces", trace)

        return {
            "type": "forensic_update",
            "timestamp": datetime.now().isoformat(),
            "ai_thinking": getattr(sys, "last_thinking", "") or engine._last_thinking,
            "ai_explanation": getattr(sys, "last_explanation", "") or engine._last_explanation,
            "module_traces": trace,
            "thinking_history": engine._thinking_history if engine._running else []
        }

    await websocket.send_json(await get_snapshot())
    queue: asyncio.Queue[bool] = asyncio.Queue()
    
    async def handler(event): await queue.put(True)
    # Forensics subscribes to more granular events
    sys.event_bus.subscribe(EventType.SIGNAL, handler)
    sys.event_bus.subscribe(EventType.DECISION_TRACE, handler)
    engine.set_update_handler(lambda x: queue.put_nowait(True))

    try:
        while True:
            await queue.get()
            await websocket.send_json(await get_snapshot())
    except WebSocketDisconnect:
        pass
    finally:
        sys.event_bus.unsubscribe(EventType.SIGNAL, handler)
        sys.event_bus.unsubscribe(EventType.DECISION_TRACE, handler)


@ws_router.websocket("/ws/telemetry")
async def telemetry_updates(websocket: WebSocket) -> None:
    """System Health WebSocket: Latency, Heartbeats, Clock Sync."""
    await websocket.accept()
    sys = get_system()
    
    async def get_snapshot():
        status = sys.get_status()
        # Use the latency from the last execution cycle
        # If no data, default to a safe 0.0
        current_latency = getattr(sys, "_last_latency_ms", 0.0)
        uptime = time.time() - getattr(sys, "_start_time", time.time())
        
        return {
            "type": "telemetry_update",
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "latency_ms": current_latency,
            "is_synced": True,
            "uptime_seconds": int(uptime)
        }

    await websocket.send_json(await get_snapshot())
    queue: asyncio.Queue[bool] = asyncio.Queue()
    async def handler(event): await queue.put(True)
    sys.event_bus.subscribe(EventType.MARKET, handler) # Pulse on every market tick

    try:
        while True:
            await queue.get()
            await websocket.send_json(await get_snapshot())
    except WebSocketDisconnect:
        pass
    finally:
        sys.event_bus.unsubscribe(EventType.MARKET, handler)


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
