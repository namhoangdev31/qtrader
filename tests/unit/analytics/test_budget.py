import logging

import pytest

from qtrader.analytics.budget import CloudBudgetGuard, ResourceGuardrail


def test_cloud_budget_guard_initialization():
    guard = CloudBudgetGuard(monthly_budget=1000.0)
    assert guard.monthly_budget == 1000.0
    assert guard.current_spend == 0.0
    assert guard.is_throttled is False

def test_cloud_budget_guard_update_spend():
    guard = CloudBudgetGuard(monthly_budget=100.0)
    guard.update_spend(50.0)
    assert guard.current_spend == 50.0
    assert guard.is_throttled is False
    
    guard.update_spend(110.0)
    assert guard.current_spend == 110.0
    assert guard.is_throttled is True

def test_cloud_budget_guard_job_eligibility():
    guard = CloudBudgetGuard(monthly_budget=100.0)
    # 0 + 50 = 50 < 110 (1.1 * 100)
    assert guard.check_job_eligibility(50.0) is True
    
    guard.update_spend(105.0)
    # 105 + 10 = 115 > 110
    assert guard.check_job_eligibility(10.0) is False
    
    guard.update_spend(120.0)
    # Throttled
    assert guard.check_job_eligibility(1.0) is False

def test_resource_guardrail_config():
    config = ResourceGuardrail.get_job_config()
    assert config["num_cpus"] == 2
    assert "memory" in config
    assert "timeout" in config
