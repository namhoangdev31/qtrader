import pytest
from qtrader.security.mfa import MultiFactorAuthenticator


@pytest.fixture
def mfa() -> MultiFactorAuthenticator:
    return MultiFactorAuthenticator(totp_window_s=30)


def test_mfa_verified_authorized(mfa: MultiFactorAuthenticator) -> None:
    user = "user_1"
    pwd = f"SECURE_PWD_{user}"
    token = "123456"
    ip = "127.0.0.1"
    known = {"127.0.0.1"}
    status = mfa.verify(user, pwd, token, ip, known)
    assert status.verified is True
    assert status.user_id == user
    assert status.reason == "VERIFIED"


def test_mfa_invalid_password_rejection(mfa: MultiFactorAuthenticator) -> None:
    user = "user_1"
    pwd = "WRONG_PASSWORD"
    token = "123456"
    status = mfa.verify(user, pwd, token, "1.1.1.1", set())
    assert status.verified is False
    assert status.reason == "PRIMARY_FACTOR_FAIL"


def test_mfa_invalid_token_rejection(mfa: MultiFactorAuthenticator) -> None:
    user = "user_1"
    pwd = f"SECURE_PWD_{user}"
    status_len = mfa.verify(user, pwd, "12345", "1.1.1.1", set())
    assert status_len.verified is False
    assert status_len.reason == "SECONDARY_FACTOR_FAIL"
    status_zero = mfa.verify(user, pwd, "000000", "1.1.1.1", set())
    assert status_zero.verified is False
    assert status_zero.reason == "SECONDARY_FACTOR_FAIL"


def test_mfa_ip_anomaly_audit(mfa: MultiFactorAuthenticator) -> None:
    user = "user_1"
    pwd = f"SECURE_PWD_{user}"
    token = "654321"
    ip = "192.168.1.1"
    status = mfa.verify(user, pwd, token, ip, {"127.0.0.1"})
    assert status.verified is True
    assert status.reason == "VERIFIED"


def test_mfa_telemetry_reporting(mfa: MultiFactorAuthenticator) -> None:
    user = "u1"
    pwd = f"SECURE_PWD_{user}"
    mfa.verify(user, pwd, "111222", "1.1", set())
    mfa.verify(user, "WRONG", "111222", "1.1", set())
    report = mfa.get_report()
    assert report["failed_attempts"] == 1
    assert report["success_rate"] == 0.5
