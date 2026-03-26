from __future__ import annotations

import dataclasses

import polars as pl


@dataclasses.dataclass(slots=True)
class SimulatedTrade:
    """Standardized virtual trade record for sandbox appraisals."""
    timestamp: int
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float = 0.0


class SimulatorAdapter:
    """
    Interface for deterministic strategy simulation.
    
    Isolates strategies from the production OMS by providing a virtual 
    matching environment for historical or synthetic data.
    """

    def __init__(self, initial_capital: float = 100000.0) -> None:
        self._initial_capital = initial_capital
        self._capital = initial_capital
        self._trades: list[SimulatedTrade] = []

    def get_equity_curve(self) -> pl.DataFrame:
        """Construct the historical PnL trajectory of the simulation."""
        if not self._trades:
            return pl.DataFrame({"timestamp": [], "equity": []})

        # Calculate cumulative PnL from trades
        # Simplification: Assume all trades are closed or marked-to-market is not needed yet
        # or assume 'trades' are realized PnL snapshots.
        # institutional-grade: use candle data to mark-to-market.
        
        # For Sandbox purposes, we focus on the realized PnL of trade pairs.
        return pl.DataFrame(self._trades)

    def process_signal(
        self, 
        timestamp: int, 
        symbol: str, 
        side: str, 
        price: float, 
        quantity: float
    ) -> SimulatedTrade | None:
        """
        Match a strategy signal into a virtual trade execution.
        """
        # Simplification: Assume instant total fill at market price for sandbox.
        # In production, we'd use the rust_core matching engine.
        trade = SimulatedTrade(
            timestamp=timestamp,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            fee=0.0 # Sandbox default
        )
        self._trades.append(trade)
        return trade

    @property
    def trades(self) -> list[SimulatedTrade]:
        return self._trades
