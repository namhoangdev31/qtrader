import pytest

from qtrader.security.rbac import (
    Permission,
    RBACProcessor,
    Role,
    rbac_required,
    set_context_user,
)


@pytest.fixture(autouse=True)
def reset_context() -> None:
    """Reset identity context before each test."""
    set_context_user("UNKNOWN", Role.TRADER)


def test_rbac_hierarchy_inheritance() -> None:
    """Verify that ADMIN inherits permissions from lower roles."""
    set_context_user("admin_user", Role.ADMIN)

    # ADMIN should have EXECUTE_TRADE (inherited via TRADER in hierarchy)
    assert RBACProcessor.check_access(Permission.EXECUTE_TRADE) is True

    # ADMIN should have OVERRIDE_RISK (explicit)
    assert RBACProcessor.check_access(Permission.OVERRIDE_RISK) is True


def test_rbac_deny_by_default() -> None:
    """Verify that TRADER cannot perform HIGH_PRIVILEGE actions."""
    set_context_user("trader_user", Role.TRADER)

    # TRADER cannot OVERRIDE_RISK
    assert RBACProcessor.check_access(Permission.OVERRIDE_RISK) is False

    # TRADER cannot MANAGE_SYSTEM
    assert RBACProcessor.check_access(Permission.MANAGE_SYSTEM) is False


def test_rbac_separation_of_duties_violation() -> None:
    """Verify that a user cannot approve their own strategy (SoD)."""
    # RISK_MANAGER has APPROVE_STRATEGY permission
    set_context_user("risk_manager_1", Role.RISK_MANAGER)

    # 1. OK: Approve someone else's strategy
    is_ok = RBACProcessor.check_access(Permission.APPROVE_STRATEGY, resource_owner_id="trader_A")
    assert is_ok is True

    # 2. DENY: Approve own strategy (Violation)
    is_denied = RBACProcessor.check_access(
        Permission.APPROVE_STRATEGY, resource_owner_id="risk_manager_1"
    )
    assert is_denied is False


@pytest.mark.asyncio
async def test_rbac_required_decorator_success() -> None:
    """Verify that the decorator authorizes valid requests."""
    set_context_user("trader_1", Role.TRADER)

    @rbac_required(Permission.EXECUTE_TRADE)
    async def place_order(symbol: str) -> str:
        return f"Order placed for {symbol}"

    result = await place_order("AAPL")
    assert result == "Order placed for AAPL"


@pytest.mark.asyncio
async def test_rbac_required_decorator_failure() -> None:
    """Verify that the decorator blocks unauthorized requests."""
    set_context_user("trader_1", Role.TRADER)

    @rbac_required(Permission.APPROVE_STRATEGY)
    async def approve_strat(owner_id: str) -> str:
        return "Approved"

    with pytest.raises(PermissionError, match="Security DENIED"):
        await approve_strat(owner_id="trader_2")


@pytest.mark.asyncio
async def test_rbac_required_decorator_sod_failure() -> None:
    """Verify that the decorator enforces SoD via owner_id kwarg."""
    # ADMIN has APPROVE_STRATEGY but cannot approve own
    set_context_user("admin_1", Role.ADMIN)

    @rbac_required(Permission.APPROVE_STRATEGY)
    async def approve_strat(owner_id: str) -> str:
        return "Approved"

    # Violation: admin_1 approving admin_1
    with pytest.raises(PermissionError, match="Security DENIED"):
        await approve_strat(owner_id="admin_1")
