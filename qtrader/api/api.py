from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from qtrader.security.jwt_auth import get_current_active_user, TokenPayload, JWTAuthManager
from qtrader.security.rbac import rbac_required, Permission
from qtrader.core.logger import log

app = FastAPI(title="QTrader HFT API", version="0.4.0")
_logger = log.bind(module="api")

# --- Security Middleware ---

# CORS: Restricted to production domains (mocked here)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Should be restricted in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers for browser protection."""
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

app.add_middleware(SecurityHeadersMiddleware)


import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Body, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Any, Dict


class QTraderAPI:
    """Wrapper for the FastAPI server lifecycle."""
    def __init__(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.host = host
        self.port = port

    def run(self) -> None:
        """Non-blocking blocking uvicorn run."""
        uvicorn.run(app, host=self.host, port=self.port)


# --- Authentication ---

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, str]:
    """Issue a JWT access token for valid credentials."""
    # Placeholder: In production, verify against DB (e.g. asyncpg)
    # We use username as subject and mock role for now
    role = "admin" if form_data.username == "hoangnam" else "viewer"
    
    auth_manager = JWTAuthManager()
    token = auth_manager.create_access_token(subject=form_data.username, role=role)
    
    _logger.info("New login", sub=form_data.username, role=role)
    return {"access_token": token, "token_type": "bearer"}


# --- Public / Health ---

@app.get("/ping")
async def ping() -> Dict[str, str]:
    """Public health check."""
    return {"status": "PONG"}


# --- Protected Endpoints with RBAC ---

@app.get("/status")
@rbac_required(Permission.READ)
async def get_status(user: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retrieve system health and fund status. Required: READ."""
    _logger.debug("Status request", sub=user["sub"])
    return {
        "running": True, # In practice, this pulls from global_orchestrator
        "mode": "SHADOW",
        "user_role": user["role"]
    }


@app.post("/orders/place")
@rbac_required(Permission.EXECUTE)
async def place_order(
    payload: Dict[str, Any],
    user: TokenPayload = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Place a manual trade override. Required: EXECUTE."""
    symbol = payload.get("symbol")
    side = payload.get("side")
    qty = payload.get("qty")
    
    _logger.info("Manual trade override", sub=user["sub"], symbol=symbol, side=side)
    
    # Logic to publish OrderEvent would go here
    return {
        "status": "ACCEPTED",
        "order_id": "man-12345",
        "meta": {"sub": user["sub"]}
    }


@app.post("/system/halt")
@rbac_required(Permission.MANAGE)
async def emergency_halt(
    reason: str = Body(..., embed=True),
    user: TokenPayload = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Trigger a global manual emergency halt. Required: MANAGE."""
    _logger.critical("MANUAL GLOBAL HALT", sub=user["sub"], reason=reason)
    
    # Logic to engage global kill switch would go here
    return {"status": "HALTED", "reason": reason, "authorizer": user["sub"]}


@app.get("/audit/history")
@rbac_required(Permission.READ)
async def get_audit_history(user: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retrieve trading audit logs. Required: READ."""
    return {
        "logs": [
            {"ts": "2026-03-26T10:00:00Z", "event": "STRATEGY_START", "details": "AlphaEngine live"},
            {"ts": "2026-03-26T10:05:00Z", "event": "ORDER_FILL", "details": "BTC/USDT BUY 0.1@68500"}
        ]
    }
