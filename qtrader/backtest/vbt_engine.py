from __future__ import annotations

import pandas as pd
import polars as pl
import vectorbt as vbt


class VBTEngine:
    """VectorBT PRO engine adapter for QTrader notebook integration.
    
    Provides an ultra-fast vectorized execution engine for signal research,
    replacing the legacy Polars-native VectorizedEngine.
    """

    def backtest(
        self,
        df: pl.DataFrame,
        signal_col: str = "signal",
        price_col: str = "close",
        init_cash: float = 100_000.0,
        fees: float = 0.0005,
        slippage: float = 0.0000,
        freq: str = "1d",
    ) -> vbt.Portfolio:
        """Run vectorized backtest and return a VectorBT Portfolio object.
        
        Args:
            df: Input DataFrame containing timestamp, prices, and signals.
            signal_col: Column containing positional signals (-1, 0, 1).
            price_col: Column to execute against.
            init_cash: Starting capital.
            fees: Fractional fee (e.g. 0.0005 for 5 bps).
            slippage: Fractional slippage per side.
            freq: Time frequency (e.g. '1d', '5m').
            
        Returns:
            VectorBT Portfolio instance with all computed stats.
        """
        # Convert to Pandas and set timestamp index for VectorBT
        pdf = df.to_pandas()
        if "timestamp" in pdf.columns:
            pdf.set_index("timestamp", inplace=True)
            
        # Extract variables
        price = pdf[price_col]
        
        # Build entries/exits from signals (-1=Short, 1=Long, 0=Flat)
        # VectorBT handles transitions automatically (e.g. going from +1 to -1)
        entries = pdf[signal_col] > 0
        exits = pdf[signal_col] < 0
        
        # Run simulation
        # Using from_signals which is clean and intuitive for simple long/short setups
        # For more complex setups, from_orders allows specifying exact sizes
        pf = vbt.Portfolio.from_signals(
            price,
            entries=entries,
            exits=exits,
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            freq=freq,
        )
        
        from qtrader.output.analytics.ev_calculator import EVCalculator
        calc = EVCalculator(portfolio=pf)
        report = calc.diagnose(target_symbol="VBT-BACKTEST", min_trades=30)
        
        return report, pf

    def optimize_crossover(
        self,
        df: pl.DataFrame,
        price_col: str,
        fast_range: range,
        slow_range: range,
        init_cash: float = 100_000.0,
        fees: float = 0.0005,
        freq: str = "1d",
    ) -> vbt.Portfolio:
        """Example: Grid search over MA crossover parameters natively in VBT.
        
        Args:
            df: Input data
            price_col: Price column
            fast_range: Range of fast moving average periods
            slow_range: Range of slow moving average periods
        """
        pdf = df.to_pandas()
        if "timestamp" in pdf.columns:
            pdf.set_index("timestamp", inplace=True)
            
        price = pdf[price_col]
        
        # Convert ranges to lists (Numba workaround for VectorBT)
        fast_list = list(fast_range)
        slow_list = list(slow_range)
        
        # Run all combinations of fast and slow MAs simultaneously
        fast_ma, slow_ma = vbt.MA.run_combs(price, fast_list, slow_list)
        
        # Determine signals across all combinations
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)
        
        # Execute portfolio across the multidimensional grid
        pf = vbt.Portfolio.from_signals(
            price, 
            entries=entries, 
            exits=exits, 
            init_cash=init_cash, 
            fees=fees,
            freq=freq
        )
        return pf
