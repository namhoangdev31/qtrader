import pytest
from qtrader.security.rbac import Role, set_context_user
from qtrader.security.secret_manager import SecretManager


@pytest.fixture
def manager() -> SecretManager:
    return SecretManager()


@pytest.fixture(autouse=True)
def reset_context() -> None:
    set_context_user("INTERNAL_SYSTEM", Role.TRADER)


def test_secret_store_and_authorized_retrieve(manager: SecretManager) -> None:
    set_context_user("trader_1", Role.TRADER)
    res_v1 = manager.store_secret("BINANCE_API_KEY", "AK12345")
    assert res_v1 == 1
    deny_val = manager.get_secret("BINANCE_API_KEY")
    assert deny_val is None
    set_context_user("admin_1", Role.ADMIN)
    allow_val = manager.get_secret("BINANCE_API_KEY")
    assert allow_val == "AK12345"


def test_secret_versioning_lifecycle(manager: SecretManager) -> None:
    set_context_user("admin_1", Role.ADMIN)
    v1 = manager.store_secret("STRATEGY_CONFIG", "v1_config")
    v2 = manager.store_secret("STRATEGY_CONFIG", "v2_config")
    assert v1 == 1 and v2 == 2
    assert manager.get_secret("STRATEGY_CONFIG") == "v2_config"
    assert manager.get_secret("STRATEGY_CONFIG", version=1) == "v1_config"


def test_secret_unauthorized_audit_telemetry(manager: SecretManager) -> None:
    set_context_user("guest_user", Role.TRADER)
    manager.store_secret("ROOT_PASS", "123456")
    manager.get_secret("ROOT_PASS")
    set_context_user("security_officer", Role.ADMIN)
    manager.get_secret("ROOT_PASS")
    report = manager.get_report()
    assert report["unauthorized_attempts"] == 1
    assert report["access_count"] == 1
