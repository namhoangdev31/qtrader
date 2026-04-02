import logging
from datetime import datetime, timedelta, timezone

import jwt
from typing_extensions import TypedDict

from qtrader.core.config import settings

_LOG = logging.getLogger("qtrader.security.jwt_auth")


class TokenPayload(TypedDict):
    """Structure of an authenticated JWT payload."""

    sub: str
    role: str
    exp: int


class JWTAuthManager:
    """Manages JWT generation and verification for the system."""

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str | None = None,
        expire_minutes: int | None = None,
    ) -> None:
        self.secret_key = secret_key or settings.jwt_secret_key
        self.algorithm = algorithm or settings.jwt_algorithm
        self.expire_minutes = expire_minutes or settings.jwt_access_token_expire_minutes

    def create_access_token(self, subject: str, role: str) -> str:
        """Create a new signed JWT access token."""
        expires_delta = timedelta(minutes=self.expire_minutes)
        expire = datetime.now(timezone.utc) + expires_delta

        payload = {
            "sub": subject,
            "role": role,
            "exp": int(expire.timestamp()),
        }

        encoded_jwt = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        _LOG.info(f"JWT_AUTH | Generated token for sub={subject} role={role}")
        return encoded_jwt

    def decode_access_token(self, token: str) -> TokenPayload:
        """Decode and verify a JWT access token.

        Raises:
            jwt.ExpiredSignatureError: If the token has expired.
            jwt.InvalidTokenError: If the token is invalid or corrupted.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            # Ensure the structure matches our typed dict
            if "sub" not in payload or "role" not in payload:
                raise jwt.InvalidTokenError("Token payload missing required claims")

            return {
                "sub": payload["sub"],
                "role": payload["role"],
                "exp": payload.get("exp", 0),
            }
        except jwt.ExpiredSignatureError:
            _LOG.warning("JWT_AUTH | Token expired")
            raise
        except jwt.InvalidTokenError as e:
            _LOG.warning(f"JWT_AUTH | Invalid token: {e}")
            raise


# --- FastAPI Integration ---

try:
    from fastapi import Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordBearer

    from qtrader.security.rbac import set_context_role

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
    _auth_manager = JWTAuthManager()

    async def get_current_user_token(token: str = Depends(oauth2_scheme)) -> TokenPayload:
        """FastAPI dependency to validate JWT token and return payload."""
        try:
            return _auth_manager.decode_access_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_current_active_user(payload: TokenPayload = Depends(get_current_user_token)) -> TokenPayload:
        """FastAPI dependency that also sets the async-safe RBAC context variable."""
        # Inject the role into the current execution context for @rbac_required decorators
        set_context_role(payload["role"])
        return payload

except ImportError:
    _LOG.debug("FastAPI not installed; skipping auth dependency injection.")
