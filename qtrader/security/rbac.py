from enum import Enum, auto


class Permission(Enum):
    """Available permissions in the system."""

    READ = auto()  # View logs, metrics, state
    EXECUTE = auto()  # Place/cancel orders
    MANAGE = auto()  # Change system config, manage users


class Role(Enum):
    """User roles in the system."""

    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"


# Role to Permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {Permission.READ, Permission.EXECUTE, Permission.MANAGE},
    Role.TRADER: {Permission.READ, Permission.EXECUTE},
    Role.VIEWER: {Permission.READ},
}


def has_permission(role: str, permission: Permission) -> bool:
    """
    Check if a role has the required permission.

    Args:
        role: The role name (str).
        permission: The Permission enum member to check.

    Returns:
        bool: True if access is granted, False otherwise.
    """
    try:
        r = Role(role)
    except ValueError:
        return False

    return permission in ROLE_PERMISSIONS.get(r, set())
