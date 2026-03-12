import asyncio
import polars as pl
from qtrader.core.bus import EventBus
from qtrader.core.event import EventType, MarketDataEvent, SignalEvent
from qtrader.data.pipeline.sources.csv_source import CSVDataSource
from qtrader.data.market.ohlcv import OHLCVNormalizer
from qtrader.data.pipeline.pipeline import SimpleDataPipeline
from qtrader.backtest.engine import BacktestEngine
from qtrader.backtest.broker_sim import SimulatedBroker
from qtrader.strategy.base import BaseStrategy
from qtrader.risk.limits import SimpleRiskManager


class MovingAverageStrategy(BaseStrategy):
    """A simple strategy that buys when price is above SMA."""
    def __init__(self, symbol: str, period: int = 20) -> None:
        super().__init__(symbol)
        self.period = period
        self.prices = []

    async def on_market_data(self, event: MarketDataEvent) -> None:
        price = event.data.get("close")
        if price is None:
            return
            
        self.prices.append(price)
        if len(self.prices) > self.period:
            self.prices.pop(0)
            sma = sum(self.prices) / len(self.prices)
            
            if price > sma:
                signal = SignalEvent(
                    symbol=self.symbol,
                    signal_type="LONG",
                    strength=1.0,
                    timestamp=event.timestamp
                )
                await bus.publish(signal)


async def main():
    # 1. Setup Event Bus
    global bus
    bus = EventBus()
    
    # 2. Setup Data Pipeline
    # Normally we'd run generate_data.py first
    source = CSVDataSource("sample_data.csv", "AAPL")
    normalizer = OHLCVNormalizer("AAPL")
    pipeline = SimpleDataPipeline(source, normalizer, bus)
    
    # 3. Setup Strategy, Broker, Risk
    strategy = MovingAverageStrategy("AAPL")
    broker = SimulatedBroker(bus)
    risk = SimpleRiskManager()
    
    # 4. Subscribe components to events
    bus.subscribe(EventType.MARKET_DATA, strategy.on_market_data)
    bus.subscribe(EventType.MARKET_DATA, broker.on_market_data)
    bus.subscribe(EventType.SIGNAL, lambda e: print(f"Signal: {e.signal_type} at {e.timestamp}"))
    
    # 5. Run Backtest
    engine = BacktestEngine(bus, [pipeline])
    print("Starting backtest...")
    await engine.run()
    print("Backtest finished.")


if __name__ == "__main__":
    # Create sample data if it doesn't exist
    import os
    if not os.path.exists("sample_data.csv"):
        from scripts.generate_data import generate_synthetic_data
        df = generate_synthetic_data("AAPL", days=1)
        df.write_csv("sample_data.csv")
        
    asyncio.run(main())
