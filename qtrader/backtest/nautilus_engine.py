from __future__ import annotations

import logging
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from typing import Any, Callable
from nautilus_trader.trading.strategy import Strategy, StrategyConfig
from nautilus_trader.model.enums import OrderSide


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
        self._instrument: Any | None = None
        self._indicators: dict[int, dict] = {}

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
            
        # Select best matching instrument from test kit to avoid complex manual creation
        # for these notebook-based experiments.
        s = self.symbol.upper()
        if "ETH" in s:
            self._instrument = TestInstrumentProvider.ethusdt_binance()
        elif "ADA" in s:
            self._instrument = TestInstrumentProvider.adausdt_binance()
        else:
            self._instrument = TestInstrumentProvider.btcusdt_binance()
            
        self._engine.add_instrument(self._instrument)
        _LOG.info(f"Instrument {self._instrument.id} added to engine.")
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
        from nautilus_trader.model.objects import Price, Quantity
        
        # Use the ID of the actual instrument added to the cache, or calculate a normalized fallback
        if self._instrument:
            instrument_id = self._instrument.id
        else:
            normalized = self.symbol.replace('/', '').replace('-', '').upper()
            instrument_id = InstrumentId.from_str(f"{normalized}.{self.venue}")

        # Fix: Using BarType.from_str is more reliable across Nautilus versions
        bar_type = BarType.from_str(f"{instrument_id}-1-HOUR-LAST-EXTERNAL")
        
        bars = []
        for row in df.to_dicts():
            bar = Bar(
                bar_type=bar_type,
                open=Price.from_str(str(row["open"])),
                high=Price.from_str(str(row["high"])),
                low=Price.from_str(str(row["low"])),
                close=Price.from_str(str(row["close"])),
                volume=Quantity.from_str(str(row["volume"])),
                ts_event=int(row["timestamp"].timestamp() * 1e9),
                ts_init=int(row["timestamp"].timestamp() * 1e9),
            )
            bars.append(bar)
            
        self._engine.add_data(bars)
        
        # Store indicators for lookup during simulation
        # Using timestamp in nanoseconds as the key
        self._indicators = {
            int(row["timestamp"].timestamp() * 1e9): row 
            for row in df.to_dicts()
        }
        
        _LOG.info(f"Added {len(bars)} bars and indicators to Nautilus for {self.symbol}")
        return self

    def add_strategy(self, strategy_fn: Callable) -> NautilusEngineAdapter:
        """Register a python function as a Nautilus strategy."""
        if not self._engine:
            raise RuntimeError("Engine not built.")
        if not self._instrument:
            raise RuntimeError("Instrument not added. Call add_instrument() first.")
            
        strategy = ProxyStrategy(
            config=ProxyStrategyConfig(),
            strategy_fn=strategy_fn,
            instrument_id=self._instrument.id,
            indicators=self._indicators
        )
        self._engine.add_strategy(strategy)
        _LOG.info(f"Strategy function {strategy_fn.__name__} registered with Nautilus.")
        return self

    def run(self) -> None:
        """Execute the backtest simulation."""
        if not self._engine:
            raise RuntimeError("Engine not built.")
        self._engine.run()
        _LOG.info("Nautilus simulation execution complete.")

    def get_report(self) -> "EVReport":
        """Generate a summary report of the simulation metrics."""
        from qtrader.output.analytics.ev_calculator import EVCalculator
        
        if not self._engine:
            return EVCalculator.build_report_from_stats(self.symbol, EVCalculator()._empty_stats())
            
        try:
            from nautilus_trader.model.identifiers import Venue
            import pandas as pd
            
            # 1. Positions Report (for trades and PnL)
            df_pos = self._engine.trader.generate_positions_report()
            
            # 2. Account Report (for balance/equity curve)
            df_acc = self._engine.trader.generate_account_report(Venue(self.venue))
            
            # Robust column identification
            # Nautilus reports often use "Realized profit/loss" or "Realized PnL"
            pnl_col = [c for c in df_pos.columns if 'pnl' in c.lower() or 'profit' in c.lower()]
            pnl_col = pnl_col[0] if pnl_col else None
            
            # Account report usually has 'Balance' or 'Equity'
            balance_col = [c for c in df_acc.columns if 'balance' in c.lower() or 'equity' in c.lower()]
            balance_col = balance_col[0] if balance_col else None
            
            # Calculate metrics
            total_trades = len(df_pos)
            win_rate = 0.0
            ev_per_trade = 0.0
            
            if total_trades > 0 and pnl_col:
                # Ensure numeric
                df_pos[pnl_col] = pd.to_numeric(df_pos[pnl_col], errors='coerce').fillna(0)
                wins = df_pos[df_pos[pnl_col] > 0]
                win_rate = len(wins) / total_trades
                ev_per_trade = float(df_pos[pnl_col].mean())
                
            equity_curve = []
            max_drawdown = 0.0
            if not df_acc.empty and balance_col:
                # Ensure numeric and sort by time if index is not chronological
                df_acc[balance_col] = pd.to_numeric(df_acc[balance_col], errors='coerce').fillna(0)
                equity_curve = df_acc[balance_col].tolist()
                
                # Simple Max Drawdown calculation
                peak = df_acc[balance_col].cummax()
                drawdown = (df_acc[balance_col] - peak) / peak
                max_drawdown = abs(float(drawdown.min())) if not drawdown.empty else 0.0
                
            _LOG.info(f"Generated report: {total_trades} trades, {win_rate:.2%} win rate, {max_drawdown:.2%} max DD")
            
            stats = EVCalculator()._empty_stats()
            stats.update({
                "total_trades": total_trades,
                "win_count": len(wins) if total_trades > 0 else 0,
                "loss_count": (total_trades - len(wins)) if total_trades > 0 else 0,
                "win_rate": win_rate,
                "loss_rate": 1.0 - win_rate if total_trades > 0 else 0.0,
                "ev_per_trade": ev_per_trade,
                "max_drawdown": max_drawdown,
                "kelly_fraction": win_rate - (1 - win_rate) / 1.0 if win_rate > 0 else 0.0,
                "equity_curve": equity_curve
            })
            return EVCalculator.build_report_from_stats(self.symbol, stats)
            
        except Exception as e:
            _LOG.error(f"Error generating real report: {e}. Falling back to empty report.")
            return EVCalculator.build_report_from_stats(self.symbol, EVCalculator()._empty_stats())

class ProxyStrategyConfig(StrategyConfig):
    pass

class ProxyStrategy(Strategy):
    def __init__(self, config, strategy_fn, instrument_id, indicators):
        super().__init__(config)
        self.strategy_fn = strategy_fn
        self.instrument_id = instrument_id
        self.indicators = indicators

    def on_bar(self, bar):
        # Look up indicators for this bar's timestamp
        row = self.indicators.get(bar.ts_event)
        if row is None:
            return

        order_event = self.strategy_fn(row)
        if order_event:
            from nautilus_trader.model.enums import OrderSide
            from nautilus_trader.model.objects import Quantity
            
            side = OrderSide.BUY if order_event.side.upper() == "BUY" else OrderSide.SELL
            order = self.order_factory.market_order(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=Quantity.from_str(str(order_event.quantity))
            )
            self.submit_order(order)

