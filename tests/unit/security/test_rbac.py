from qtrader.security.rbac import Permission, Role, has_permission


def test_admin_permissions() -> None:
    """Admin should have all permissions."""
    role = Role.ADMIN.value
    assert has_permission(role, Permission.READ) is True
    assert has_permission(role, Permission.EXECUTE) is True
    assert has_permission(role, Permission.MANAGE) is True


def test_trader_permissions() -> None:
    """Trader should have read and execute but not manage."""
    role = Role.TRADER.value
    assert has_permission(role, Permission.READ) is True
    assert has_permission(role, Permission.EXECUTE) is True
    assert has_permission(role, Permission.MANAGE) is False


def test_viewer_permissions() -> None:
    """Viewer should only have read permission."""
    role = Role.VIEWER.value
    assert has_permission(role, Permission.READ) is True
    assert has_permission(role, Permission.EXECUTE) is False
    assert has_permission(role, Permission.MANAGE) is False


def test_invalid_role() -> None:
    """Invalid role should have no permissions."""
    assert has_permission("invalid_role", Permission.READ) is False
    assert has_permission("", Permission.EXECUTE) is False
    assert has_permission("super_admin", Permission.MANAGE) is False


def test_none_role() -> None:
    """None or empty role should be handled gracefully."""
    # mypy --strict will prevent passing None, but let's test string-based roles
    assert has_permission("none", Permission.READ) is False
