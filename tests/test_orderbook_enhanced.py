#!/usr/bin/env python3
"""Test script for OrderbookEnhanced."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from decimal import Decimal
from datetime import datetime
from qtrader.core.types import OrderEvent
from qtrader.execution.orderbook_enhanced import OrderbookEnhanced
from qtrader.execution.slippage_model import SlippageModel
from qtrader.execution.latency_model import LatencyModel

async def test_orderbook_enhanced():
    """Test the enhanced orderbook simulator."""
    print("Testing OrderbookEnhanced...")
    
    # Create orderbook simulator
    orderbook = OrderbookEnhanced(
        symbols=["AAPL"],
        base_spread_bps=5.0,
        depth_levels=10,
        volume_per_level=1000.0,
        liquidity_decay_factor=0.8
    )
    
    # Create slippage and latency models
    slippage_model = SlippageModel()
    latency_model = LatencyModel(
        base_network_latency_ms=10.0,
        network_jitter_ms=2.0,
        base_processing_latency_ms=5.0,
        processing_jitter_ms=1.0
    )
    
    # Test getting initial orderbook
    book = await orderbook.get_orderbook("AAPL")
    print(f"Initial orderbook bids: {len(book['bids'])} levels")
    print(f"Initial orderbook asks: {len(book['asks'])} levels")
    print(f"Best bid: {book['bids'][0][0] if book['bids'] else 'None'}")
    print(f"Best ask: {book['asks'][0][0] if book['asks'] else 'None'}")
    
    # Test market buy order
    buy_order = OrderEvent(
        order_id="test_buy_1",
        symbol="AAPL",
        timestamp=datetime.now(),
        order_type="MARKET",
        side="BUY",
        quantity=Decimal('100')
    )
    
    print("\nExecuting market buy order for 100 shares...")
    fill = await orderbook.execute_order(
        symbol="AAPL",
        order=buy_order,
        slippage_model=slippage_model,
        latency_model=latency_model,
        deterministic=True  # Use deterministic for testing
    )
    
    print(f"Fill result:")
    print(f"  Order ID: {fill.order_id}")
    print(f"  Symbol: {fill.symbol}")
    print(f"  Side: {fill.side}")
    print(f"  Quantity: {fill.quantity}")
    print(f"  Price: {fill.price}")
    print(f"  Commission: {fill.commission}")
    if fill.metadata:
        print(f"  Latency: {fill.metadata.get('latency_ms', 0):.2f} ms")
        print(f"  Fees paid: {fill.metadata.get('fees_paid', 0):.4f}")
    
    # Test market sell order
    sell_order = OrderEvent(
        order_id="test_sell_1",
        symbol="AAPL",
        timestamp=datetime.now(),
        order_type="MARKET",
        side="SELL",
        quantity=Decimal('50')
    )
    
    print("\nExecuting market sell order for 50 shares...")
    fill = await orderbook.execute_order(
        symbol="AAPL",
        order=sell_order,
        slippage_model=slippage_model,
        latency_model=latency_model,
        deterministic=True
    )
    
    print(f"Fill result:")
    print(f"  Order ID: {fill.order_id}")
    print(f"  Symbol: {fill.symbol}")
    print(f"  Side: {fill.side}")
    print(f"  Quantity: {fill.quantity}")
    print(f"  Price: {fill.price}")
    print(f"  Commission: {fill.commission}")
    if fill.metadata:
        print(f"  Latency: {fill.metadata.get('latency_ms', 0):.2f} ms")
        print(f"  Fees paid: {fill.metadata.get('fees_paid', 0):.4f}")
    
    # Test limit order (non-marketable)
    limit_order = OrderEvent(
        order_id="test_limit_1",
        symbol="AAPL",
        timestamp=datetime.now(),
        order_type="LIMIT",
        side="BUY",
        quantity=Decimal('100'),
        price=Decimal('90.0')  # Well below market - should rest as maker
    )
    
    print("\nExecuting non-marketable limit buy order at $90.00...")
    fill = await orderbook.execute_order(
        symbol="AAPL",
        order=limit_order,
        slippage_model=slippage_model,
        latency_model=latency_model,
        deterministic=True
    )
    
    print(f"Fill result:")
    print(f"  Order ID: {fill.order_id}")
    print(f"  Symbol: {fill.symbol}")
    print(f"  Side: {fill.side}")
    print(f"  Quantity: {fill.quantity}")
    print(f"  Price: {fill.price}")
    print(f"  Commission: {fill.commission}")
    if fill.metadata:
        print(f"  Latency: {fill.metadata.get('latency_ms', 0):.2f} ms")
        print(f"  Fees paid: {fill.metadata.get('fees_paid', 0):.4f}")
        print(f"  Was marketable: {fill.metadata.get('was_marketable', True)}")
    
    # Test liquidity profile
    print("\nLiquidity profile for AAPL:")
    liquidity = orderbook.get_liquidity_profile("AAPL")
    for key, value in liquidity.items():
        print(f"  {key}: {value}")
    
    print("\nOrderbookEnhanced test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_orderbook_enhanced())