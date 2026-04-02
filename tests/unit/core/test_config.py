import os
from pathlib import Path

import pytest

from qtrader.core.config import Config, QTraderSettings


def test_config_default_values():
    settings = QTraderSettings()
    assert settings.simulate_mode is True
    assert settings.log_level == "INFO"
    assert "BTC/USDT" in settings.MLFLOW_EXPERIMENT_NAME or settings.MLFLOW_EXPERIMENT_NAME == "qtrader_v4_autonomous"

def test_config_env_override(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "test_key")
    monkeypatch.setenv("SIMULATE_MODE", "False")
    
    # Reload settings or create new instance
    settings = QTraderSettings(binance_api_key="test_key", simulate_mode=False)
    assert settings.binance_api_key == "test_key"
    assert settings.simulate_mode is False
    assert settings.BINANCE_API_KEY == "test_key"

def test_config_resolve_paths():
    settings = QTraderSettings(datalake_uri="test_lake", db_path="test.db")
    assert Path(settings.datalake_uri).is_absolute()
    assert Path(settings.db_path).is_absolute()
    assert settings.datalake_uri.endswith("test_lake")

def test_config_live_mode_validation():
    # Live mode without API keys should raise ValueError
    with pytest.raises(ValueError, match="Live mode requires at least one exchange API key"):
        QTraderSettings(simulate_mode=False, binance_api_key="", coinbase_api_key="")

def test_config_singleton():
    from qtrader.core.config import Config as cfg1
    from qtrader.core.config import settings as cfg2
    assert cfg1 is cfg2
