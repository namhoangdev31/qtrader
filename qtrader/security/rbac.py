import asyncio
import functools
import logging
from collections.abc import Callable
from contextvars import ContextVar
from enum import Enum, auto
from typing import Any, Final, TypeVar

T = TypeVar("T", bound=Callable[..., Any])
_LOG = logging.getLogger("qtrader.security.rbac")


class Permission(Enum):
    """
    Industrial RBAC Permissions.
    """

    EXECUTE_TRADE = auto()
    READ_PROD_DATA = auto()
    OVERRIDE_RISK = auto()
    MANAGE_SYSTEM = auto()
    APPROVE_STRATEGY = auto()
    VIEW_AUDIT = auto()


class Role(Enum):
    """
    Industrial RBAC Roles.
    """

    ADMIN = "ADMIN"
    RISK_MANAGER = "RISK_MANAGER"
    TRADER = "TRADER"
    AUDITOR = "AUDITOR"
    SYSTEM = "SYSTEM"


# Role Hierarchy Definition: Higher roles inherit from lower ones.
# Hierarchy Flattened Map for deterministic O(1) resolution.
ROLE_HIERARCHY: Final[dict[Role, set[Role]]] = {
    Role.ADMIN: {Role.ADMIN, Role.RISK_MANAGER, Role.TRADER, Role.AUDITOR, Role.SYSTEM},
    Role.RISK_MANAGER: {Role.RISK_MANAGER, Role.TRADER, Role.AUDITOR},
    Role.TRADER: {Role.TRADER},
    Role.AUDITOR: {Role.AUDITOR},
    Role.SYSTEM: {Role.SYSTEM},
}

# Immutable Permission Matrix: Base permissions assigned to each role.
ROLE_PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = {
    Role.ADMIN: frozenset(
        [
            Permission.EXECUTE_TRADE,
            Permission.READ_PROD_DATA,
            Permission.OVERRIDE_RISK,
            Permission.MANAGE_SYSTEM,
            Permission.APPROVE_STRATEGY,
            Permission.VIEW_AUDIT,
        ]
    ),
    Role.RISK_MANAGER: frozenset(
        [Permission.READ_PROD_DATA, Permission.OVERRIDE_RISK, Permission.APPROVE_STRATEGY]
    ),
    Role.TRADER: frozenset([Permission.EXECUTE_TRADE, Permission.READ_PROD_DATA]),
    Role.AUDITOR: frozenset([Permission.READ_PROD_DATA, Permission.VIEW_AUDIT]),
    Role.SYSTEM: frozenset([Permission.READ_PROD_DATA, Permission.MANAGE_SYSTEM]),
}

# Context variables for user tracking (Async / Thread safe)
current_user_id: ContextVar[str] = ContextVar("current_user_id", default="INTERNAL_SYSTEM")
current_user_role: ContextVar[Role] = ContextVar("current_user_role", default=Role.TRADER)


class RBACProcessor:
    """
    Identity Access Control Engine.

    Objective: Enforce zero-trust RBAC with hierarchy and Separation of Duties (SoD).
    Every access decision MUST be logged for regulatory forensic reconstruction.
    """

    @staticmethod
    def check_access(permission: Permission, resource_owner_id: str | None = None) -> bool:
        """
        Terminal Authorization Logic.

        Decision Rules:
        1. Resolve effective permissions through Role Hierarchy.
        2. Deny by Default: If permission not in set -> 0.
        3. Separation of Duties: Users cannot approve their own resources (SoD).

        Args:
            permission: The requested Permission.
            resource_owner_id: Optional ID of the resource owner for SoD checks.

        Returns:
            bool: ALLOW (True) / DENY (False)
        """
        user_id = current_user_id.get()
        user_role = current_user_role.get()

        # 1. Resolve Effective Permissions
        effective_roles = ROLE_HIERARCHY.get(user_role, {user_role})
        effective_perms: set[Permission] = set()
        for r in effective_roles:
            effective_perms.update(ROLE_PERMISSIONS.get(r, frozenset()))

        # 2. Permission Authority Check
        if permission not in effective_perms:
            _LOG.error(
                f"[RBAC] DENY | User={user_id} Role={user_role.value} "
                f"Action={permission.name} | Insufficient permissions"
            )
            return False

        # 3. Separation of Duties (SoD) enforcement
        # Industrial Rule: Prevents 'Trader approves own strategy' risk vector.
        if (
            permission == Permission.APPROVE_STRATEGY
            and resource_owner_id is not None
            and user_id == resource_owner_id
        ):
            _LOG.error(
                f"[RBAC] DENY | User={user_id} Action={permission.name} | "
                "SoD Violation: Resource owner cannot approve own resource"
            )
            return False

        _LOG.info(f"[RBAC] ALLOW | User={user_id} Role={user_role.value} Action={permission.name}")
        return True


def rbac_required(permission: Permission) -> Callable[[T], T]:
    """
    Principal RBAC Decorator for project governance.
    Enforces security boundaries on both async and sync execution paths.
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            owner_id = kwargs.get("owner_id")
            if not RBACProcessor.check_access(permission, owner_id):
                msg = f"Institutional Security DENIED request for {permission.name}"
                raise PermissionError(msg)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            owner_id = kwargs.get("owner_id")
            if not RBACProcessor.check_access(permission, owner_id):
                msg = f"Institutional Security DENIED request for {permission.name}"
                raise PermissionError(msg)
            return func(*args, **kwargs)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper  # type: ignore

    return decorator


def set_context_user(user_id: str, role: Role) -> Any:
    """Set identity context for the current execution thread."""
    current_user_id.set(user_id)
    return current_user_role.set(role)
