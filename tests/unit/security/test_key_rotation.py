import time

import pytest

from qtrader.security.key_rotation import KeyRotator


@pytest.fixture
def rotator() -> KeyRotator:
    """Initialize a KeyRotator with a short window for simulation."""
    # Simulation: 30s window instead of 30d
    return KeyRotator(rotation_days=0)  # Window will be 0, all keys stale immediately for test


def test_key_creation_and_registration(rotator: KeyRotator) -> None:
    """Verify that a new key can be registered and retrieved."""
    key_id = "EXCHANGE_API"
    val = rotator.create_key(key_id)
    assert len(val) > 40

    report = rotator.get_rotation_report()
    assert report["active_secrets"] == 1


def test_stale_key_identification(rotator: KeyRotator) -> None:
    """Verify that keys exceeding the window are flagged for rotation."""
    # 1. Create a key with 30-day window (mocked by 0s window in fixture)
    kid = "STALE_KEY"
    rotator.create_key(kid)

    # 2. Key should be stale immediately due to 0s window
    stale = rotator.identify_stale_keys()
    # Need to wait a tiny bit because create_key uses time.time()
    time.sleep(0.01)
    stale = rotator.identify_stale_keys()
    assert kid in stale


def test_rotation_logic_and_new_key_generation(rotator: KeyRotator) -> None:
    """Verify that rotating an existing key generates a fresh secret."""
    kid = "PROD_SECRET"
    val_v1 = rotator.create_key(kid)

    # Rotate
    val_v2 = rotator.rotate_key(kid)
    assert val_v1 != val_v2

    report = rotator.get_rotation_report()
    assert report["rotation_events"] == 1
    assert report["active_secrets"] == 1


def test_emergency_rotation_tracking(rotator: KeyRotator) -> None:
    """Verify that emergency (manual) rotations are tracked and logged."""
    kid = "SENSITIVE_KEY"
    rotator.create_key(kid)

    # Emergency trigger
    rotator.rotate_key(kid, urgent=True)

    report = rotator.get_rotation_report()
    assert report["rotation_events"] == 1


def test_unauthorized_rotation_rejection(rotator: KeyRotator) -> None:
    """Verify that attempting to rotate a non-existent key fails."""
    with pytest.raises(ValueError, match="Rotation target ID MISSING not found"):
        rotator.rotate_key("MISSING")

    report = rotator.get_rotation_report()
    assert report["failed_rotations"] == 1
