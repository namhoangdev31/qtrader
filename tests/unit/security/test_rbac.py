import pytest
from qtrader.security.rbac import Permission, RBACProcessor, Role, rbac_required, set_context_user


@pytest.fixture(autouse=True)
def reset_context() -> None:
    set_context_user("UNKNOWN", Role.TRADER)


def test_rbac_hierarchy_inheritance() -> None:
    set_context_user("admin_user", Role.ADMIN)
    assert RBACProcessor.check_access(Permission.EXECUTE_TRADE) is True
    assert RBACProcessor.check_access(Permission.OVERRIDE_RISK) is True


def test_rbac_deny_by_default() -> None:
    set_context_user("trader_user", Role.TRADER)
    assert RBACProcessor.check_access(Permission.OVERRIDE_RISK) is False
    assert RBACProcessor.check_access(Permission.MANAGE_SYSTEM) is False


def test_rbac_separation_of_duties_violation() -> None:
    set_context_user("risk_manager_1", Role.RISK_MANAGER)
    is_ok = RBACProcessor.check_access(Permission.APPROVE_STRATEGY, resource_owner_id="trader_A")
    assert is_ok is True
    is_denied = RBACProcessor.check_access(
        Permission.APPROVE_STRATEGY, resource_owner_id="risk_manager_1"
    )
    assert is_denied is False


@pytest.mark.asyncio
async def test_rbac_required_decorator_success() -> None:
    set_context_user("trader_1", Role.TRADER)

    @rbac_required(Permission.EXECUTE_TRADE)
    async def place_order(symbol: str) -> str:
        return f"Order placed for {symbol}"

    result = await place_order("AAPL")
    assert result == "Order placed for AAPL"


@pytest.mark.asyncio
async def test_rbac_required_decorator_failure() -> None:
    set_context_user("trader_1", Role.TRADER)

    @rbac_required(Permission.APPROVE_STRATEGY)
    async def approve_strat(owner_id: str) -> str:
        return "Approved"

    with pytest.raises(PermissionError, match="Security DENIED"):
        await approve_strat(owner_id="trader_2")


@pytest.mark.asyncio
async def test_rbac_required_decorator_sod_failure() -> None:
    set_context_user("admin_1", Role.ADMIN)

    @rbac_required(Permission.APPROVE_STRATEGY)
    async def approve_strat(owner_id: str) -> str:
        return "Approved"

    with pytest.raises(PermissionError, match="Security DENIED"):
        await approve_strat(owner_id="admin_1")
