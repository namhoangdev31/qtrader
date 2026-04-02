import random

import numpy as np
import pytest
import torch

from qtrader.core.seed_manager import SeedManager


def test_seed_manager_consistency():
    # Identical inputs must yield identical global seeds
    sm1 = SeedManager(strategy_id="BTC_STDEV", timestamp="2026-01-01T00:00:00", environment="backtest")
    sm2 = SeedManager(strategy_id="BTC_STDEV", timestamp="2026-01-01T00:00:00", environment="backtest")
    
    assert sm1.global_seed == sm2.global_seed
    assert sm1.global_seed > 0

def test_module_seed_derivation():
    sm = SeedManager(strategy_id="BTC_STDEV", timestamp="2026-01-01T00:00:00", environment="backtest")
    
    s_alpha = sm.get_module_seed("alpha_core")
    s_exec = sm.get_module_seed("execution_engine")
    
    # Seeds must be different for different modules
    assert s_alpha != s_exec
    
    # Seeds must be deterministic
    assert s_alpha == sm.get_module_seed("alpha_core")

def test_apply_injection():
    sm = SeedManager(strategy_id="TEST", timestamp="2026-01-01T00:00:00", environment="dev")
    sm.apply_global()
    
    # State 1
    r1 = random.random()
    n1 = np.random.rand()
    t1 = torch.rand(1).item()
    
    # Re-apply should not change state or should be idempotent
    sm.apply_global()
    
    # Resetting libraries manually to check reproducibility
    random.seed(sm.global_seed)
    np.random.seed(sm.global_seed)
    torch.manual_seed(sm.global_seed)
    
    assert random.random() == r1
    assert np.random.rand() == n1
    assert torch.rand(1).item() == t1

def test_from_config_factory():
    sm = SeedManager.from_config("STRAT_1", "2026-01-01", simulate_mode=True)
    assert sm.environment == "backtest"
    
    sm_live = SeedManager.from_config("STRAT_1", "2026-01-01", simulate_mode=False)
    assert sm_live.environment == "live"
