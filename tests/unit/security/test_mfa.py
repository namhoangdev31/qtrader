import pytest

from qtrader.security.mfa import MultiFactorAuthenticator


@pytest.fixture
def mfa() -> MultiFactorAuthenticator:
    """Initialize MultiFactorAuthenticator with 30s defaults."""
    return MultiFactorAuthenticator(totp_window_s=30)


def test_mfa_verified_authorized(mfa: MultiFactorAuthenticator) -> None:
    """Verify that a correct password and token authorize a success."""
    user = "user_1"
    pwd = f"SECURE_PWD_{user}"
    token = "123456"  # noqa: S105
    ip = "127.0.0.1"
    known = {"127.0.0.1"}

    status = mfa.verify(user, pwd, token, ip, known)
    assert status.verified is True  # noqa: S101
    assert status.user_id == user  # noqa: S101
    assert status.reason == "VERIFIED"  # noqa: S101


def test_mfa_invalid_password_rejection(mfa: MultiFactorAuthenticator) -> None:
    """Verify that an incorrect password fails even with a valid token."""
    user = "user_1"
    pwd = "WRONG_PASSWORD"  # noqa: S105
    token = "123456"  # noqa: S105

    status = mfa.verify(user, pwd, token, "1.1.1.1", set())
    assert status.verified is False  # noqa: S101
    assert status.reason == "PRIMARY_FACTOR_FAIL"  # noqa: S101


def test_mfa_invalid_token_rejection(mfa: MultiFactorAuthenticator) -> None:
    """Verify that an incorrect token (e.g., zero or wrong length) is rejected."""
    user = "user_1"
    pwd = f"SECURE_PWD_{user}"

    # 1. Invalid length (must be 6)
    status_len = mfa.verify(user, pwd, "12345", "1.1.1.1", set())
    assert status_len.verified is False  # noqa: S101
    assert status_len.reason == "SECONDARY_FACTOR_FAIL"  # noqa: S101

    # 2. Block zero token
    status_zero = mfa.verify(user, pwd, "000000", "1.1.1.1", set())
    assert status_zero.verified is False  # noqa: S101
    assert status_zero.reason == "SECONDARY_FACTOR_FAIL"  # noqa: S101


def test_mfa_ip_anomaly_audit(mfa: MultiFactorAuthenticator) -> None:
    """Verify that an unknown IP triggers a success if factors are valid (audit warning only)."""
    user = "user_1"
    pwd = f"SECURE_PWD_{user}"
    token = "654321"  # noqa: S105
    ip = "192.168.1.1"  # Not in known_ips

    status = mfa.verify(user, pwd, token, ip, {"127.0.0.1"})
    # It still authorizes if factors match (industrial continuity)
    assert status.verified is True  # noqa: S101
    assert status.reason == "VERIFIED"  # noqa: S101


def test_mfa_telemetry_reporting(mfa: MultiFactorAuthenticator) -> None:
    """Verify that telemetry correctly identifies failed attempts."""
    user = "u1"
    pwd = f"SECURE_PWD_{user}"

    # 1. SUCCESS
    mfa.verify(user, pwd, "111222", "1.1", set())
    # 2. FAIL
    mfa.verify(user, "WRONG", "111222", "1.1", set())

    report = mfa.get_report()
    assert report["failed_attempts"] == 1  # noqa: S101
    assert report["success_rate"] == 0.5  # noqa: S101, PLR2004
