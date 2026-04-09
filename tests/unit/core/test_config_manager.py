import asyncio
import uuid
import pytest
from qtrader.core.config_manager import ConfigManager
from qtrader.core.events import ConfigChangeEvent


@pytest.mark.asyncio
async def test_config_versioning_lifecycle():
    initial = {"max_pos": 100, "trading_enabled": True}
    manager = ConfigManager(initial_config=initial)
    evt1 = await manager.update("max_pos", 500)
    assert manager.get_current_version() == 2
    assert manager.get("max_pos") == 500
    assert manager.get("trading_enabled") is True
    assert evt1.payload.old_value == 100
    assert evt1.payload.new_value == 500
    await manager.update("fee_rate", 0.001)
    assert manager.get_current_version() == 3
    assert manager.get("fee_rate") == 0.001


@pytest.mark.asyncio
async def test_full_snapshot_rollback_integrity():
    initial = {"risk": 1.0, "fees": 0.001}
    manager = ConfigManager(initial_config=initial)
    await manager.update("risk", 5.0)
    await manager.update("fees", 0.005)
    assert manager.get("risk") == 5.0
    assert manager.get("fees") == 0.005
    evt_rollback = await manager.rollback(1)
    assert manager.get_current_version() == 4
    assert manager.get("risk") == 1.0
    assert manager.get("fees") == 0.001
    assert evt_rollback.payload.config_key == "SYSTEM_FORCE_ROLLBACK"
    assert evt_rollback.payload.new_value == "V1"


@pytest.mark.asyncio
async def test_invalid_rollback_version_error():
    manager = ConfigManager(initial_config={"test": 1})
    with pytest.raises(ValueError) as exc:
        await manager.rollback(999)
    assert "version 999 does not exist" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_config_event_bus_deserialization():
    manager = ConfigManager(initial_config={"k": "v"})
    evt = await manager.update("k", "v_new")
    assert isinstance(evt, ConfigChangeEvent)
    assert evt.payload.config_key == "k"
    assert evt.payload.old_value == "v"
    assert evt.payload.new_value == "v_new"
    assert evt.payload.version == 2
