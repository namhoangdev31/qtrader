"""FastAPI Server Entrypoint."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from qtrader.api.dependencies import get_system
from qtrader.api.router import health_router, router, ws_router

# Locate the static/templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: Run the trading system logic in the background
    system = get_system()
    bg_task = asyncio.create_task(system.start())
    yield
    # Shutdown
    await system.stop()
    bg_task.cancel()

app = FastAPI(
    title="QTrader API",
    description="FastAPI Backend for Paper Trading UI",
    version="1.0.0",
    lifespan=lifespan
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

# Ensure templates dir exists
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Serve the static UI
@app.get("/", response_class=HTMLResponse, response_model=None)
async def index() -> HTMLResponse:
    """Serve the root index HTML."""
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>QTrader UI: index.html not found!</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    # Optional direct run
    uvicorn.run("qtrader.api.server:app", host="0.0.0.0", port=8000, reload=True)  # noqa: S104
