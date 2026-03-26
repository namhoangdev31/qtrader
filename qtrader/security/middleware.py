"""Security middleware for FastAPI endpoints.

Provides JWT authentication + RBAC enforcement as a unified middleware layer,
ensuring every protected request goes through:
  1. JWT token extraction and validation
  2. Role injection into async-safe ContextVar
  3. Permission enforcement per endpoint

This module bridges security/jwt_auth.py and security/rbac.py into a single
composable middleware suitable for both FastAPI and raw ASGI usage.
"""
import logging
import time
from typing import Any, Callable

from qtrader.security.jwt_auth import JWTAuthManager, TokenPayload
from qtrader.security.rbac import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    current_user_role,
    set_context_role,
)

_LOG = logging.getLogger("qtrader.security.middleware")


def check_permission(user_role: str, action: Permission) -> None:
    """Validate that a user's role grants the required permission.

    Args:
        user_role: The role string extracted from the JWT payload.
        action: The Permission enum value required for the action.

    Raises:
        PermissionError: If the role does not include the required permission.
    """
    try:
        role = Role(user_role)
    except ValueError:
        _LOG.error(f"RBAC | Unknown role '{user_role}', defaulting to VIEWER")
        role = Role.VIEWER

    granted = ROLE_PERMISSIONS.get(role, set())
    if action not in granted:
        _LOG.error(
            f"RBAC | FORBIDDEN: role={role.value} action={action.name}"
        )
        raise PermissionError(
            f"Role '{role.value}' does not have '{action.name}' permission"
        )
    _LOG.debug(f"RBAC | ALLOWED: role={role.value} action={action.name}")


class SecurityMiddleware:
    """ASGI-compatible middleware that authenticates JWT and sets RBAC context.

    Usage with FastAPI:
        app.add_middleware(SecurityMiddleware, jwt_manager=JWTAuthManager())

    Public paths (e.g. /ping, /token, /docs) bypass authentication.
    """

    # Paths that do not require authentication
    PUBLIC_PATHS: set[str] = {"/ping", "/token", "/docs", "/openapi.json", "/redoc"}

    def __init__(
        self,
        app: Any,
        jwt_manager: JWTAuthManager | None = None,
    ) -> None:
        self.app = app
        self.jwt_manager = jwt_manager or JWTAuthManager()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI entrypoint."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip public endpoints
        if path in self.PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        # Extract Authorization header
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8")

        if not auth_header.startswith("Bearer "):
            await self._send_401(send, "Missing or malformed Authorization header")
            return

        token = auth_header[len("Bearer "):]

        try:
            payload: TokenPayload = self.jwt_manager.decode_access_token(token)
        except Exception as exc:
            _LOG.warning(f"JWT validation failed: {exc}")
            await self._send_401(send, "Invalid or expired token")
            return

        # Inject role into async-safe ContextVar for downstream @rbac_required
        set_context_role(payload["role"])
        _LOG.debug(f"Authenticated sub={payload['sub']} role={payload['role']}")

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_401(send: Any, detail: str) -> None:
        """Send a 401 Unauthorized ASGI response."""
        body = f'{{"detail":"{detail}"}}'.encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"content-type", b"application/json"],
                [b"www-authenticate", b"Bearer"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
