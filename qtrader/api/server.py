"""FastAPI Server Entrypoint."""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from qtrader.api.dependencies import get_system
from qtrader.api.router import health_router, router, session_router, sim_router, ws_router

logger = logging.getLogger("qtrader.api.server")

# Locate the static/templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    system = get_system()
    ui_only = os.getenv("UI_ONLY_MODE", "false").lower() == "true"
    sim_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"
    logger.info(f"API Dashboard lifespan: UI_ONLY_MODE={ui_only}, SIMULATION_MODE={sim_mode}")

    bg_task = None
    sim_task = None
    if not ui_only:
        logger.info("FULL_MODE: Waiting for manual session activation")
        await system.event_bus.start()
        try:
            await asyncio.wait_for(system.state_store.sync_from_remote(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("STATE_STORE | Remote sync timed out during startup")
    else:
        await system.event_bus.start()
        try:
            await asyncio.wait_for(system.state_store.sync_from_remote(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("STATE_STORE | Remote sync timed out during startup")
        
        logger.info(
            f"UI_ONLY_MODE: EventBus started, running={system.event_bus._running}, "
            f"workers={len(system.event_bus._worker_tasks)}"
        )
        bg_task = asyncio.create_task(_ui_heartbeat(system))
        logger.info("UI_ONLY_MODE: Heartbeat loop started")

    if sim_mode:
        from qtrader.api.router import start_simulation
        await start_simulation(system)
        logger.info("[SIM] Simulation Engine auto-started in lifespan")

    yield
    await system.stop()
    if bg_task:
        bg_task.cancel()
    from qtrader.api.router import stop_simulation
    await stop_simulation()


async def _ui_heartbeat(system: Any) -> None:
    """Publish periodic SYSTEM events so WebSocket clients stay connected and get updates."""
    from qtrader.core.events import EventType, SystemEvent, SystemPayload

    while True:
        try:
            await asyncio.sleep(5)
            balance = await system.broker.get_paper_balance()
            event = SystemEvent(
                event_type=EventType.SYSTEM,
                source="api_dashboard",
                payload=SystemPayload(
                    action="HEARTBEAT",
                    reason="UI heartbeat — periodic state update",
                    metadata={
                        "equity": balance["equity"],
                        "realized_pnl": balance["realized_pnl"],
                        "total_commissions": balance["total_commissions"],
                    },
                ),
            )
            await system.event_bus.publish(event)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[HEARTBEAT] Error in UI heartbeat: {e}", exc_info=True)


app = FastAPI(
    title="QTrader API",
    description="FastAPI Backend for Paper Trading UI",
    version="1.0.0",
    lifespan=lifespan,
)

# ADD CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(health_router)
app.include_router(router)
app.include_router(ws_router)
app.include_router(sim_router)
app.include_router(session_router)

# Ensure templates dir exists
os.makedirs(TEMPLATES_DIR, exist_ok=True)


# Serve the static UI
@app.get("/", response_class=HTMLResponse, response_model=None)
async def index() -> HTMLResponse:
    """Serve the root index HTML."""
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>QTrader UI: index.html not found!</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn

    # Optional direct run
    uvicorn.run("qtrader.api.server:app", host="0.0.0.0", port=8000, reload=True)  # noqa: S104
