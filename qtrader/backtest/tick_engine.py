"""Tick engine execution simulator wrapping the Rust core simulator."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl
import numpy as np

# Import the compiled Rust extension
try:
    import qtrader_core
except ImportError:
    qtrader_core = None

__all__ = ["RustTickEngine", "TickEngineConfig"]

_LOG = logging.getLogger("qtrader.backtest.tick_engine")

@dataclass
class TickEngineConfig:
    """Configuration for the Rust execution simulator."""
    initial_capital: float = 100_000.0
    latency_ms: int = 50           # ms network/exchange latency
    fee_rate: float = 0.0005       # 5 bps
    slippage_bps: float = 2.0      # 2 bps fixed slippage
    max_position_usd: float = 500_000.0  # Max size allowed
    max_drawdown_pct: float = 0.20 # 20% hard limit before halt

class RustTickEngine:
    """High-fidelity tick execution simulator using Rust.
    
    Replaces VectorizedEngine when precision matching, TWAP slicing, 
    and hard risk limits are required.
    """
    
    def __init__(self, config: TickEngineConfig | None = None) -> None:
        self.config = config or TickEngineConfig()
        
        if qtrader_core is None:
            raise ImportError(
                "qtrader_core Rust extension is not installed. "
                "Compile it using `cd rust_core && maturin develop --release`"
            )
        
        # Initialize Rust config object
        self._rust_config = qtrader_core.SimulatorConfig(
            initial_capital=self.config.initial_capital,
            latency_ms=self.config.latency_ms,
            fee_rate=self.config.fee_rate,
            slippage_bps=self.config.slippage_bps,
            max_position_usd=self.config.max_position_usd,
            max_drawdown_pct=self.config.max_drawdown_pct,
        )

    def run(
        self,
        df: pl.DataFrame,
        signal_col: str,
        symbol: str = "ASSET",
    ) -> dict[str, pl.Series | float]:
        """Run the tick simulator over historical data.
        
        Args:
            df: Historical dataframe containing timestamp, close, and signal.
            signal_col: Column containing trading signals.
            symbol: Name of the asset being simulated.
            
        Returns:
            Dictionary with 'equity_curve' (Series) and 'final_equity' (float).
        """
        if df.is_empty():
            _LOG.warning("RustTickEngine: Empty dataframe provided.")
            return {"final_equity": self.config.initial_capital}

        if signal_col not in df.columns:
            raise ValueError(f"Signal column '{signal_col}' not found in df.")

        # Ensure timestamp is castable to integer ms
        if df["timestamp"].dtype == pl.Datetime:
            # Polars datetime is usually in microseconds, convert to ms
            ts_array = df["timestamp"].dt.epoch(time_unit="ms").to_numpy().astype(np.int64)
        else:
            # Fallback for plain integers or floats
            ts_array = df["timestamp"].to_numpy().astype(np.int64)

        closes_array = df["close"].to_numpy().astype(np.float64)
        signals_array = df[signal_col].to_numpy().astype(np.float64)

        # Drop into Rust Extension (Zero Copy via PyO3 numpy wrapper)
        _LOG.info("RustTickEngine: Starting C++ / Rust core simulation...")
        equity_np, final_eq = qtrader_core.run_simulation_1d(
            self._rust_config,
            symbol,
            ts_array,
            closes_array,
            signals_array,
        )

        return {
            "equity_curve": pl.Series("equity", equity_np),
            "final_equity": final_eq,
        }

