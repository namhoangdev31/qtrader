from unittest.mock import MagicMock, patch
import pytest
from qtrader.core.dynamic_config import config_manager
from qtrader.strategy.manager import StrategyManager


def test_strategy_manager_init():
    sm = StrategyManager(symbol="BTC-USD")
    assert "MOMENTUM" in sm.get_strategy_names()
    assert sm.active_strategy_name == "MOMENTUM"


def test_strategy_manager_switching():
    sm = StrategyManager(symbol="BTC-USD")
    with patch.object(config_manager, "get", return_value="PROBABILISTIC"):
        strat = sm.active_strategy
        assert sm.active_strategy_name == "PROBABILISTIC"
        assert strat.__class__.__name__ == "ProbabilisticStrategy"


def test_strategy_manager_fallback():
    sm = StrategyManager(symbol="BTC-USD")
    with patch.object(config_manager, "get", return_value="INVALID_STRAT"):
        strat = sm.active_strategy
        assert sm.active_strategy_name == "MOMENTUM"
        assert strat.__class__.__name__ == "TimeSeriesMomentum"
