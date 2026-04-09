from __future__ import annotations
import dataclasses
import polars as pl


@dataclasses.dataclass(slots=True)
class SimulatedTrade:
    timestamp: int
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float = 0.0


class SimulatorAdapter:
    def __init__(self, initial_capital: float = 100000.0) -> None:
        self._initial_capital = initial_capital
        self._capital = initial_capital
        self._trades: list[SimulatedTrade] = []

    def get_equity_curve(self) -> pl.DataFrame:
        if not self._trades:
            return pl.DataFrame({"timestamp": [], "equity": []})
        return pl.DataFrame(self._trades)

    def process_signal(
        self, timestamp: int, symbol: str, side: str, price: float, quantity: float
    ) -> SimulatedTrade | None:
        trade = SimulatedTrade(
            timestamp=timestamp, symbol=symbol, side=side, price=price, quantity=quantity, fee=0.0
        )
        self._trades.append(trade)
        return trade

    @property
    def trades(self) -> list[SimulatedTrade]:
        return self._trades
