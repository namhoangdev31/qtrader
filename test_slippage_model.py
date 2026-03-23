#!/usr/bin/env python3
"""Test script for SlippageModel."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from decimal import Decimal
from qtrader.execution.slippage_model import SlippageModel

def test_slippage_model():
    """Test the slippage model."""
    print("Testing SlippageModel...")
    
    model = SlippageModel()
    
    # Create a simple orderbook
    orderbook = {
        'bids': [[Decimal('99.5'), Decimal('10')], [Decimal('99.4'), Decimal('20')]],
        'asks': [[Decimal('100.5'), Decimal('10')], [Decimal('100.6'), Decimal('20')]]
    }
    
    # Test compute_slippage
    slippage = model.compute_slippage(
        symbol="TEST",
        side="BUY",
        quantity=Decimal('5'),
        orderbook=orderbook,
        volatility=Decimal('0.02')
    )
    print(f"Slippage for BUY 5: {slippage}")
    
    slippage = model.compute_slippage(
        symbol="TEST",
        side="SELL",
        quantity=Decimal('5'),
        orderbook=orderbook,
        volatility=Decimal('0.02')
    )
    print(f"Slippage for SELL 5: {slippage}")
    
    # Test with zero quantity
    slippage = model.compute_slippage(
        symbol="TEST",
        side="BUY",
        quantity=Decimal('0'),
        orderbook=orderbook,
        volatility=Decimal('0.02')
    )
    print(f"Slippage for BUY 0: {slippage}")
    
    # Test with large quantity (should trigger volume limit)
    slippage = model.compute_slippage(
        symbol="TEST",
        side="BUY",
        quantity=Decimal('1000'),
        orderbook=orderbook,
        volatility=Decimal('0.02')
    )
    print(f"Slippage for BUY 1000: {slippage}")
    
    print("SlippageModel test completed!")

if __name__ == "__main__":
    test_slippage_model()