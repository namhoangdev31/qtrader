from __future__ import annotations

import logging
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.test_kit.providers import TestInstrumentProvider


_LOG = logging.getLogger("qtrader.backtest.nautilus")


class NautilusEngineAdapter:
    """Wrapper making NautilusTrader accessible from QTrader notebooks.
    
    Provides a high-precision, sub-millisecond, event-driven backtesting engine
    to replace the legacy PaperTradingEngine.
    """

    def __init__(self, symbol: str = "BTC/USDT", venue: str = "BINANCE"):
        self.symbol = symbol
        self.venue = venue
        self._engine: BacktestEngine | None = None

    def build(self) -> NautilusEngineAdapter:
        """Instantiate the Nautilus engine with default high-performance settings."""
        config = BacktestEngineConfig(
            logging=LoggingConfig(log_level="ERROR"),
        )
        self._engine = BacktestEngine(config=config)
        _LOG.info("NautilusTrader Engine initialized.")
        return self

    def add_venue(self, starting_balance: float = 100_000.0) -> NautilusEngineAdapter:
        """Configure a simulated crypto venue with a starting cash balance."""
        if not self._engine:
            raise RuntimeError("Engine not built. Call build() first.")
            
        self._engine.add_venue(
            Venue(self.venue),
            OmsType.NETTING,
            AccountType.MARGIN,
            [Money(starting_balance, USD)],
            base_currency=USD,
        )
        _LOG.info(f"Venue {self.venue} added with {starting_balance} USD baseline.")
        return self

    def add_instrument(self) -> NautilusEngineAdapter:
        """Add the target instrument (e.g., BTC/USD) to the simulated venue."""
        if not self._engine:
            raise RuntimeError("Engine not built. Call build() first.")
            
        # Using a standard crypto pair from the test kit
        instrument = TestInstrumentProvider.btcusdt_binance()
        self._engine.add_instrument(instrument)
        _LOG.info(f"Instrument {instrument.id} added to engine.")
        return self

    def add_data(self, df: pl.DataFrame) -> NautilusEngineAdapter:
        """Add bar data from a Polars DataFrame to the engine.
        
        Expected columns: timestamp, open, high, low, close, volume.
        """
        if not self._engine:
            raise RuntimeError("Engine not built. Call build() first.")
            
        from nautilus_trader.model.data import Bar, BarType, BarSpecification
        from nautilus_trader.model.enums import PriceType, AggregationSource
        from nautilus_trader.model.identifiers import InstrumentId
        
        instrument_id = InstrumentId.from_str(f"{self.symbol.replace('/', '')}.{self.venue}")
        # Fix: BarType requires BarSpecification instance
        bar_spec = BarSpecification.from_str("1-HOUR-LAST-INTERNAL") 
        bar_type = BarType(instrument_id, bar_spec)
        
        bars = []
        for row in df.to_dicts():
            bar = Bar(
                bar_type=bar_type,
                open=Money(row["open"], USD),
                high=Money(row["high"], USD),
                low=Money(row["low"], USD),
                close=Money(row["close"], USD),
                volume=row["volume"],
                ts_event=int(row["timestamp"].timestamp() * 1e9),
                ts_init=int(row["timestamp"].timestamp() * 1e9),
            )
            bars.append(bar)
            
        self._engine.add_data(bars)
        _LOG.info(f"Added {len(bars)} bars to Nautilus for {self.symbol}")
        return self

    def run(self) -> None:
        """Execute the backtest simulation."""
        if not self._engine:
            raise RuntimeError("Engine not built.")
        self._engine.run()
        _LOG.info("Nautilus simulation execution complete.")
