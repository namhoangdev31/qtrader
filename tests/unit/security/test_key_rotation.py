from datetime import datetime, timedelta
from unittest.mock import patch

from qtrader.security.key_rotation import KeyRotationManager


def test_key_generation() -> None:
    """Generated keys should be unique and valid initially."""
    manager = KeyRotationManager()
    key1 = manager.generate_key()
    key2 = manager.generate_key()

    assert key1 != key2
    assert manager.is_valid(key1) is True
    assert manager.is_valid(key2) is True


def test_key_revocation() -> None:
    """Revoked keys should no longer be valid."""
    manager = KeyRotationManager()
    key = manager.generate_key()
    assert manager.is_valid(key) is True

    assert manager.revoke_key(key) is True
    assert manager.is_valid(key) is False


def test_key_rotation() -> None:
    """Rotating a key should revoke the old one and return a new valid one."""
    manager = KeyRotationManager()
    old_key = manager.generate_key()

    new_key = manager.rotate_key(old_key)
    assert new_key is not None
    assert new_key != old_key
    assert manager.is_valid(old_key) is False
    assert manager.is_valid(new_key) is True


def test_invalid_key_rotation() -> None:
    """Rotating an invalid key should return None."""
    manager = KeyRotationManager()
    assert manager.rotate_key("non_existent_key") is None


def test_key_expiry() -> None:
    """Keys should automatically expire after the rotation period."""
    rotation_days = 30
    manager = KeyRotationManager(rotation_days=rotation_days)

    with patch("qtrader.security.key_rotation.datetime") as mock_datetime:
        # Initial creation at now()
        start_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = start_time
        key = manager.generate_key()
        assert manager.is_valid(key) is True

        # Test just before expiry
        mock_datetime.now.return_value = start_time + timedelta(days=rotation_days - 1)
        assert manager.is_valid(key) is True

        # Test exactly at expiry (still valid for the sake of the test logic > vs >=)
        mock_datetime.now.return_value = start_time + timedelta(days=rotation_days)
        assert manager.is_valid(key) is True

        # Test just after expiry
        mock_datetime.now.return_value = start_time + timedelta(days=rotation_days, seconds=1)
        assert manager.is_valid(key) is False


def test_revoke_non_existent_key() -> None:
    """Revoking a non-existent key should return False."""
    manager = KeyRotationManager()
    assert manager.revoke_key("not_there") is False
