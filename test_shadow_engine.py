#!/usr/bin/env python3
"""Test script for ShadowEngine."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from qtrader.core.event_bus import EventBus
from qtrader.core.types import SignalEvent, MarketData, FillEvent, EventType
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.execution.orderbook_enhanced import OrderbookEnhanced
from qtrader.execution.slippage_model import SlippageModel
from qtrader.execution.latency_model import LatencyModel

# Simple logger adapter to match LoggerProtocol
class SimpleLoggerAdapter:
    def __init__(self, logger):
        self.logger = logger
    
    def info(self, message: str, **kwargs) -> None:
        self.logger.info(message)
    
    def warning(self, message: str, **kwargs) -> None:
        self.logger.warning(message)
    
    def error(self, message: str, **kwargs) -> None:
        self.logger.error(message)
    
    def debug(self, message: str, **kwargs) -> None:
        self.logger.debug(message)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_shadow_engine():
    """Test the shadow engine functionality."""
    logger.info("Starting shadow engine test...")
    
    # Create event bus
    event_bus = EventBus(logger=SimpleLoggerAdapter(logger))
    
    # Create components
    orderbook_sim = OrderbookEnhanced(symbols=["AAPL"], base_spread_bps=5.0)
    slippage_model = SlippageModel()
    latency_model = LatencyModel(
        base_network_latency_ms=10.0,
        network_jitter_ms=2.0,
        base_processing_latency_ms=5.0,
        processing_jitter_ms=1.0
    )
    
    # Create shadow engine config
    config = {
        "shadow_mode": True,
        "data_lake_path": "./test_data_lake/shadow",
        "orderbook_simulator": orderbook_sim,
        "slippage_model": slippage_model,
        "latency_model": latency_model,
        "event_bus": event_bus
    }
    
    # Create shadow engine
    shadow_engine = ShadowEngine(config)
    
    # Start event bus and shadow engine
    await event_bus.start()
    await shadow_engine.start()
    
    try:
        # Create a test signal
        signal = SignalEvent(
            symbol="AAPL",
            timestamp=datetime.now(),
            signal_type="LONG",
            strength=Decimal('0.8')
        )
        
        # Create test market data
        market_data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=Decimal('150.0'),
            high=Decimal('151.0'),
            low=Decimal('149.0'),
            close=Decimal('150.5'),
            volume=Decimal('1000')
        )
        
        # Publish signal and market data
        logger.info("Publishing signal...")
        await event_bus.publish(EventType.SIGNALS, signal)
        
        logger.info("Publishing market data...")
        await event_bus.publish(EventType.MARKET_DATA, market_data)
        
        # Wait a bit for processing
        await asyncio.sleep(0.1)
        
        # Check metrics
        metrics = shadow_engine.get_metrics()
        logger.info(f"Shadow engine metrics: {metrics}")
        
        # Create a test fill to simulate live execution
        fill = FillEvent(
            order_id="test_order_1",
            symbol="AAPL",
            timestamp=datetime.now(),
            side="BUY",
            quantity=Decimal('0.8'),
            price=Decimal('150.6'),  # Slight slippage
            commission=Decimal('0.001')
        )
        
        # Publish fill
        logger.info("Publishing fill...")
        await event_bus.publish(EventType.FILLS, fill)
        
        # Wait a bit for processing
        await asyncio.sleep(0.1)
        
        # Check updated metrics
        metrics = shadow_engine.get_metrics()
        logger.info(f"Updated shadow engine metrics: {metrics}")
        
        logger.info("Shadow engine test completed successfully!")
        
    finally:
        # Cleanup
        await shadow_engine.stop()
        await event_bus.stop()

if __name__ == "__main__":
    asyncio.run(test_shadow_engine())