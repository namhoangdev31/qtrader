#!/usr/bin/env python3
"""Test script for NetworkKillSwitch."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from qtrader.risk.network_kill_switch import NetworkKillSwitch
from qtrader.execution.oms_adapter import OMSAdapter
from qtrader.core.types import AllocationWeights, RiskMetrics, OrderEvent
from decimal import Decimal
from datetime import datetime

# Mock OMSAdapter
class MockOMSAdapter(OMSAdapter):
    def __init__(self):
        super().__init__("MockOMSAdapter")
        self.cancel_all_orders_called = False
        self.create_order_called = False
    
    async def create_order(self, allocation_weights: AllocationWeights, risk_metrics: RiskMetrics) -> OrderEvent:
        self.create_order_called = True
        # Return a mock order event
        return OrderEvent(
            order_id="MOCK_ORDER",
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
            metadata={}
        )
    
    async def cancel_all_orders(self):
        self.cancel_all_orders_called = True

async def test_network_kill_switch():
    """Test the network kill switch."""
    print("Testing NetworkKillSwitch...")
    
    # Create mock OMS adapter
    mock_oms_adapter = MockOMSAdapter()
    
    # Create kill switch with oms_adapter
    kill_switch = NetworkKillSwitch(
        oms_adapter=mock_oms_adapter,
        logger_instance=None
    )
    
    # Initial state
    assert not kill_switch.is_engaged(), "Kill switch should not be engaged initially"
    assert kill_switch.get_mode() is None
    assert kill_switch.get_status()["triggered_at"] is None
    assert kill_switch.get_status()["trigger_reason"] is None
    
    # Engage hard kill
    await kill_switch.engage_hard_kill("Test reason")
    
    # Give a little time for the background tasks to run
    await asyncio.sleep(0.01)
    
    assert kill_switch.is_engaged(), "Kill switch should be engaged"
    assert kill_switch.get_mode() == 'hard'
    assert kill_switch.get_status()["triggered_at"] is not None
    assert kill_switch.get_status()["trigger_reason"] == "Test reason"
    assert mock_oms_adapter.cancel_all_orders_called, "OMS adapter cancel_all_orders should have been called"
    
    # Test soft stop
    # First, disengage
    await kill_switch.disengage()
    assert not kill_switch.is_engaged()
    
    # Now engage soft stop
    await kill_switch.engage_soft_stop("Soft stop reason")
    assert kill_switch.is_engaged()
    assert kill_switch.get_mode() == 'soft'
    assert kill_switch.get_status()["triggered_at"] is not None
    assert kill_switch.get_status()["trigger_reason"] == "Soft stop reason"
    # For soft stop, we don't expect the OMS adapter cancel_all_orders to have been called
    # Disengage from soft stop before testing hard kill again
    await kill_switch.disengage()
    assert not kill_switch.is_engaged()
    
    # Reset the mock to see if it's called on hard kill
    mock_oms_adapter.cancel_all_orders_called = False
    # Engage hard kill again to see if OMS adapter is called
    await kill_switch.engage_hard_kill("Hard kill reason")
    await asyncio.sleep(0.01)
    assert mock_oms_adapter.cancel_all_orders_called, "OMS adapter cancel_all_orders should have been called on hard kill"
    
    # Disengage
    await kill_switch.disengage()
    assert not kill_switch.is_engaged()
    assert kill_switch.get_mode() is None
    assert kill_switch.get_status()["triggered_at"] is None
    assert kill_switch.get_status()["trigger_reason"] is None
    
    print("NetworkKillSwitch test passed!")

if __name__ == "__main__":
    asyncio.run(test_network_kill_switch())