import time
import pytest
from qtrader.security.key_rotation import KeyRotator


@pytest.fixture
def rotator() -> KeyRotator:
    return KeyRotator(rotation_days=0)


def test_key_creation_and_registration(rotator: KeyRotator) -> None:
    key_id = "EXCHANGE_API"
    val = rotator.create_key(key_id)
    assert len(val) > 40
    report = rotator.get_rotation_report()
    assert report["active_secrets"] == 1


def test_stale_key_identification(rotator: KeyRotator) -> None:
    kid = "STALE_KEY"
    rotator.create_key(kid)
    stale = rotator.identify_stale_keys()
    time.sleep(0.01)
    stale = rotator.identify_stale_keys()
    assert kid in stale


def test_rotation_logic_and_new_key_generation(rotator: KeyRotator) -> None:
    kid = "PROD_SECRET"
    val_v1 = rotator.create_key(kid)
    val_v2 = rotator.rotate_key(kid)
    assert val_v1 != val_v2
    report = rotator.get_rotation_report()
    assert report["rotation_events"] == 1
    assert report["active_secrets"] == 1


def test_emergency_rotation_tracking(rotator: KeyRotator) -> None:
    kid = "SENSITIVE_KEY"
    rotator.create_key(kid)
    rotator.rotate_key(kid, urgent=True)
    report = rotator.get_rotation_report()
    assert report["rotation_events"] == 1


def test_unauthorized_rotation_rejection(rotator: KeyRotator) -> None:
    with pytest.raises(ValueError, match="Rotation target ID MISSING not found"):
        rotator.rotate_key("MISSING")
    report = rotator.get_rotation_report()
    assert report["failed_rotations"] == 1
