import pytest
import yaml
from pathlib import Path
from qtrader.core.config_loader import ConfigLoader, QTraderConfig

@pytest.fixture
def valid_config_dict():
    return {
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

def test_config_loader_valid(tmp_path, valid_config_dict):
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(valid_config_dict, f)
    
    ConfigLoader.reset()
    config = ConfigLoader.load(config_file)
    
    assert config.version == "1.0.0"
    assert config.risk.max_leverage == 2.0
    assert config.execution.retry_policy == "exponential"
    assert config.strategy.feature_flags.hft_optimizations is True

def test_config_loader_invalid_bounds(tmp_path, valid_config_dict):
    # Set invalid max_drawdown > 1.0
    valid_config_dict["risk"]["max_drawdown"] = 1.5
    
    config_file = tmp_path / "config_bad.yaml"
    with open(config_file, "w") as f:
        yaml.dump(valid_config_dict, f)
    
    ConfigLoader.reset()
    # In qtrader, invalid config triggers sys.exit(1)
    with pytest.raises(SystemExit) as excinfo:
        ConfigLoader.load(config_file)
    
    assert excinfo.value.code == 1

def test_config_loader_missing_field(tmp_path, valid_config_dict):
    # Remove mandatory version field
    del valid_config_dict["version"]
    
    config_file = tmp_path / "config_missing.yaml"
    with open(config_file, "w") as f:
        yaml.dump(valid_config_dict, f)
    
    ConfigLoader.reset()
    with pytest.raises(SystemExit) as excinfo:
        ConfigLoader.load(config_file)
    
    assert excinfo.value.code == 1

def test_config_loader_singleton(tmp_path, valid_config_dict):
    config_file = tmp_path / "config_single.yaml"
    with open(config_file, "w") as f:
        yaml.dump(valid_config_dict, f)
    
    ConfigLoader.reset()
    c1 = ConfigLoader.load(config_file)
    c2 = ConfigLoader.load() # Load cached instance
    
    assert c1 is c2
