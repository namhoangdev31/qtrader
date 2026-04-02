"""Tests for [SECURITY_CORE_SYSTEM]: RBAC + JWT + Middleware."""
import pytest

from qtrader.security.jwt_auth import JWTAuthManager
from qtrader.security.middleware import SecurityMiddleware, check_permission
from qtrader.security.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    current_user_role,
    rbac_required,
    set_context_role,
)


class TestRBACPermissions:
    """Validate RBAC role-permission matrix."""

    def test_admin_has_all_permissions(self) -> None:
        assert ROLE_PERMISSIONS[Role.ADMIN] == {
            Permission.READ, Permission.EXECUTE, Permission.MANAGE, Permission.OVERRIDE
        }

    def test_viewer_has_read_only(self) -> None:
        assert ROLE_PERMISSIONS[Role.VIEWER] == {Permission.READ}

    def test_trader_cannot_manage(self) -> None:
        assert Permission.MANAGE not in ROLE_PERMISSIONS[Role.TRADER]

    def test_risk_officer_cannot_execute(self) -> None:
        assert Permission.EXECUTE not in ROLE_PERMISSIONS[Role.RISK_OFFICER]


class TestCheckPermission:
    """Validate the check_permission utility."""

    def test_admin_can_execute(self) -> None:
        check_permission("admin", Permission.EXECUTE)  # Should not raise

    def test_viewer_cannot_execute(self) -> None:
        with pytest.raises(PermissionError):
            check_permission("viewer", Permission.EXECUTE)

    def test_unknown_role_defaults_to_viewer(self) -> None:
        # Unknown role falls back to VIEWER which has only READ
        check_permission("unknown_role", Permission.READ)  # OK
        with pytest.raises(PermissionError):
            check_permission("unknown_role", Permission.EXECUTE)


class TestJWTAuth:
    """Validate JWT token lifecycle."""

    def test_create_and_decode_token(self) -> None:
        mgr = JWTAuthManager(secret_key="test-secret", algorithm="HS256", expire_minutes=30)
        token = mgr.create_access_token(subject="trader1", role="trader")

        payload = mgr.decode_access_token(token)
        assert payload["sub"] == "trader1"
        assert payload["role"] == "trader"

    def test_invalid_token_raises(self) -> None:
        import jwt as pyjwt
        mgr = JWTAuthManager(secret_key="test-secret", algorithm="HS256", expire_minutes=30)
        with pytest.raises(pyjwt.InvalidTokenError):
            mgr.decode_access_token("invalid.token.here")


class TestRBACDecorator:
    """Validate @rbac_required decorator enforcement."""

    @pytest.mark.asyncio
    async def test_rbac_allowed(self) -> None:
        set_context_role("admin")

        @rbac_required(Permission.EXECUTE)
        async def do_trade() -> str:
            return "executed"

        result = await do_trade()
        assert result == "executed"

    @pytest.mark.asyncio
    async def test_rbac_denied(self) -> None:
        set_context_role("viewer")

        @rbac_required(Permission.EXECUTE)
        async def do_trade() -> str:
            return "executed"

        with pytest.raises(PermissionError):
            await do_trade()
