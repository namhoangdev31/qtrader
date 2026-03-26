import functools
import logging
from contextvars import ContextVar
from enum import Enum, auto
from typing import Any, Callable, TypeVar

logger = logging.getLogger("qtrader.security")

T = TypeVar("T", bound=Callable[..., Any])


class Permission(Enum):
    """Available permissions in the system."""

    READ = auto()       # View logs, metrics, state
    EXECUTE = auto()    # Place/cancel orders
    MANAGE = auto()     # Change system config, risk limits
    OVERRIDE = auto()  # Manual trade override


class Role(Enum):
    """User roles in the system."""

    ADMIN = "admin"
    TRADER = "trader"
    RISK_OFFICER = "risk_officer"
    VIEWER = "viewer"


# Role to Permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {Permission.READ, Permission.EXECUTE, Permission.MANAGE, Permission.OVERRIDE},
    Role.TRADER: {Permission.READ, Permission.EXECUTE},
    Role.RISK_OFFICER: {Permission.READ, Permission.MANAGE},
    Role.VIEWER: {Permission.READ},
}

# ContextVar to track the role of the current execution context (async safe)
current_user_role: ContextVar[Role] = ContextVar("current_user_role", default=Role.VIEWER)


def rbac_required(permission: Permission) -> Callable[[T], T]:
    """Decorator to enforce role-based access control on an async/sync function."""

    def decorator(func: T) -> T:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            role = current_user_role.get()
            if permission not in ROLE_PERMISSIONS.get(role, set()):
                logger.error(f"RBAC | Access DENIED: Role={role.value} Permission={permission.name} Action={func.__name__}")
                raise PermissionError(f"Role {role.value} does not have {permission.name} permission")
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            role = current_user_role.get()
            if permission not in ROLE_PERMISSIONS.get(role, set()):
                logger.error(f"RBAC | Access DENIED: Role={role.value} Permission={permission.name} Action={func.__name__}")
                raise PermissionError(f"Role {role.value} does not have {permission.name} permission")
            return func(*args, **kwargs)

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper  # type: ignore

    return decorator


def set_context_role(role_name: str) -> Any:
    """Set the security role for the current context."""
    try:
        role = Role(role_name)
    except ValueError:
        role = Role.VIEWER
    return current_user_role.set(role)
