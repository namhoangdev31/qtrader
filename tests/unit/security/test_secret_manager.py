import pytest

from qtrader.security.rbac import Role, set_context_user
from qtrader.security.secret_manager import SecretManager


@pytest.fixture
def manager() -> SecretManager:
    """Initialize SecretManager with a volatile master key."""
    return SecretManager()


@pytest.fixture(autouse=True)
def reset_context() -> None:
    """Ensure context is reset before each security test."""
    set_context_user("INTERNAL_SYSTEM", Role.TRADER)


def test_secret_store_and_authorized_retrieve(manager: SecretManager) -> None:
    """Verify that an authorized ADMIN can retrieve a stored secret."""
    # TRADER cannot read prod data (set in fixture above)
    set_context_user("trader_1", Role.TRADER)
    res_v1 = manager.store_secret("BINANCE_API_KEY", "AK12345")
    assert res_v1 == 1

    # 1. DENY: Trader attempting to read
    deny_val = manager.get_secret("BINANCE_API_KEY")
    assert deny_val is None

    # 2. ALLOW: ADMIN attempting to read
    set_context_user("admin_1", Role.ADMIN)
    allow_val = manager.get_secret("BINANCE_API_KEY")
    assert allow_val == "AK12345"


def test_secret_versioning_lifecycle(manager: SecretManager) -> None:
    """Verify that updating a secret creates a separate immutable version."""
    set_context_user("admin_1", Role.ADMIN)

    # Version 1
    v1 = manager.store_secret("STRATEGY_CONFIG", "v1_config")
    # Version 2
    v2 = manager.store_secret("STRATEGY_CONFIG", "v2_config")

    assert v1 == 1 and v2 == 2

    # Retrieve latest (default)
    assert manager.get_secret("STRATEGY_CONFIG") == "v2_config"
    # Retrieve historical
    assert manager.get_secret("STRATEGY_CONFIG", version=1) == "v1_config"


def test_secret_unauthorized_audit_telemetry(manager: SecretManager) -> None:
    """Verify that unauthorized access attempts are correctly tracked."""
    # 1. Unauthorized Attempt
    set_context_user("guest_user", Role.TRADER)
    manager.store_secret("ROOT_PASS", "123456")
    manager.get_secret("ROOT_PASS")  # Should be denied

    # 2. Authorized Attempt
    set_context_user("security_officer", Role.ADMIN)
    manager.get_secret("ROOT_PASS")  # Should be granted

    report = manager.get_report()
    assert report["unauthorized_attempts"] == 1
    assert report["access_count"] == 1
