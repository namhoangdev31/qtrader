import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from qtrader.core.config import Config

app = FastAPI(title="QTrader v4 Live Monitoring")

# Global state tracker (ideally this would be a shared object or singleton)
# For now, we'll use a simple dictionary that the engine will update
stats = {
    "start_time": datetime.now(Config.tz),
    "last_heartbeat": None,
    "iteration": 0,
    "regime": "None",
    "active_model": "None",
    "exposure_btc": 0.0,
    "status": "Starting"
}

@app.get("/")
async def root():
    return {"message": "QTrader v4 Live API is active"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(Config.tz)}

@app.get("/status")
async def get_status() -> dict[str, Any]:
    uptime = datetime.now(Config.tz) - stats["start_time"]
    return {
        "uptime_seconds": uptime.total_seconds(),
        "iteration": stats["iteration"],
        "last_heartbeat": stats["last_heartbeat"],
        "regime": stats["regime"],
        "active_model": stats["active_model"],
        "total_exposure_btc": stats["exposure_btc"],
        "engine_status": stats["status"],
        "system_info": {
            "platform": os.uname().sysname,
            "machine": os.uname().machine,
            "python_version": os.sys.version
        }
    }
