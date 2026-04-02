import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.config_loader import ConfigLoader, QTraderConfig
from qtrader.core.dynamic_config_manager import DynamicConfigManager


@pytest.fixture
def mock_config_bus():
    bus = MagicMock()
    bus.publish_change = AsyncMock()
    return bus

@pytest.fixture(autouse=True)
def setup_config(tmp_path):
    # Create initial valid config
    config_data = {
        "version": "1.0.0",
        "risk": {
            "max_drawdown": 0.1,
            "max_leverage": 2.0,
            "var_limit": 0.01,
            "kill_switch_enabled": True
        },
        "execution": {
            "slippage_limit_bps": 10,
            "latency_budget_ms": 50,
            "retry_policy": "exponential",
            "simulated_fill": False
        },
        "strategy": {
            "min_signal_strength": 0.6,
            "lookback_window": 15,
            "feature_flags": {
                "hft_optimizations": True,
                "risk_check_pre_trade": True
            }
        },
        "infrastructure": {
            "timeout_ms": 1000,
            "concurrency_limit": 5,
            "buffer_size": 512
        }
    }
    
    import yaml
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    
    ConfigLoader.reset()
    ConfigLoader.load(config_file)
    yield
    ConfigLoader.reset()

@pytest.mark.asyncio
async def test_dynamic_config_update_valid(mock_config_bus):
    manager = DynamicConfigManager(config_event_bus=mock_config_bus)
    
    # 1. Update slippage_limit_bps
    delta = {"execution": {"slippage_limit_bps": 30}}
    success = await manager.update_config(delta)
    
    assert success is True
    assert ConfigLoader.load().execution.slippage_limit_bps == 30
    mock_config_bus.publish_change.assert_called_once()
    assert manager.update_count == 1

@pytest.mark.asyncio
async def test_dynamic_config_max_delta_violation(mock_config_bus):
    manager = DynamicConfigManager(config_event_bus=mock_config_bus, leverage_delta_limit=0.5)
    
    # 1. Attempt to increase leverage from 2.0 to 10.0 (> 50% change)
    delta = {"risk": {"max_leverage": 10.0}}
    success = await manager.update_config(delta)
    
    assert success is False
    # Configuration should remain unchanged
    assert ConfigLoader.load().risk.max_leverage == 2.0
    mock_config_bus.publish_change.assert_not_called()
    assert manager.failure_count == 1

@pytest.mark.asyncio
async def test_dynamic_config_invalid_schema(mock_config_bus):
    manager = DynamicConfigManager(config_event_bus=mock_config_bus)
    
    # 1. Invalid value type (string instead of int)
    delta = {"infrastructure": {"concurrency_limit": "not-an-int"}}
    success = await manager.update_config(delta)
    
    assert success is False
    assert manager.failure_count == 1

@pytest.mark.asyncio
async def test_dynamic_config_rollback(mock_config_bus):
    manager = DynamicConfigManager(config_event_bus=mock_config_bus)
    
    # 1. First valid update
    await manager.update_config({"execution": {"slippage_limit_bps": 20}})
    assert ConfigLoader.load().execution.slippage_limit_bps == 20
    
    # 2. Second valid update
    await manager.update_config({"execution": {"slippage_limit_bps": 40}})
    assert ConfigLoader.load().execution.slippage_limit_bps == 40
    
    # 3. Rollback
    await manager.rollback()
    assert ConfigLoader.load().execution.slippage_limit_bps == 20
    assert manager.rollback_count == 1
