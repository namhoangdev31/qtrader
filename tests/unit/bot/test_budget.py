import pytest
from unittest.mock import MagicMock
from qtrader.bot.budget import BudgetManager

def test_budget_manager_initialization():
    manager = BudgetManager(monthly_limit=1000.0)
    assert manager.monthly_limit == 1000.0
    assert manager.current_spend == 0.0

def test_budget_manager_record_spend():
    manager = BudgetManager(monthly_limit=100.0)
    manager.record_spend(50.0)
    assert manager.current_spend == 50.0
    
    assert manager.is_within_budget() is True
    
    manager.record_spend(60.0)
    assert manager.current_spend == 110.0
    assert manager.is_within_budget() is False

def test_budget_manager_reset():
    manager = BudgetManager(monthly_limit=100.0)
    manager.record_spend(50.0)
    manager.reset()
    assert manager.current_spend == 0.0
