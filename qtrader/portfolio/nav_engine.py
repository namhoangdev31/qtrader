from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from qtrader.core.events import NAVEvent, NAVPayload

if TYPE_CHECKING:
    from qtrader.core.state_store import SystemState

logger = logging.getLogger(__name__)

try:
    from qtrader_core import Account, PortfolioEngine
    _HAS_RUST = True
except ImportError:
    logger.warning("NAV_ENGINE | Rust core (qtrader_core) not found. Falling back to Python implementation.")
    _HAS_RUST = False


class NAVEngine:
    """
    Real-time Net Asset Value (NAV) and Portfolio Accounting Engine.
    Provides institutional-grade Mark-to-Market (MtM) valuation and PnL separation.

    NAV = Cash + PortfolioMarketValue - CumulativeFees
    """

    def __init__(self) -> None:
        if _HAS_RUST:
            self._rust_engine = PortfolioEngine()

    def compute(
        self, state: SystemState, mark_prices: dict[str, Decimal], trace_id: UUID | None = None
    ) -> NAVEvent:
        """
        Compute the latest NAV and PnL breakdown for the given system state.
        
        Institutional Requirement: Must use high-performance Rust backend.
        """
        if not _HAS_RUST:
            raise RuntimeError("NAV_ENGINE | Rust core (qtrader_core) is required but not found. Build the rust extension to proceed.")

        # 1. Prepare Account state for Rust
        account = Account(float(state.cash))
        account.cash = float(state.cash)
        
        for symbol, pos in state.positions.items():
            account.add_position_direct(symbol, float(pos.quantity), float(pos.average_price))

        # 2. Conversion of mark_prices to float dict
        float_prices = {sym: float(p) for sym, p in mark_prices.items()}

        # 3. Compute via Rust
        report = self._rust_engine.compute_nav(account, float_prices, float(state.total_fees))

        # 4. Aggregate Realized PnL (still tracked in state for now)
        total_realized_pnl = sum(pos.realized_pnl for pos in state.positions.values())

        return NAVEvent(
            trace_id=trace_id or uuid4(),
            source="NAVEngineRust",
            payload=NAVPayload(
                nav=Decimal(str(report.nav)),
                cash=Decimal(str(report.cash)),
                realized_pnl=total_realized_pnl,
                unrealized_pnl=Decimal(str(report.unrealized_pnl)),
                total_fees=Decimal(str(report.total_fees)),
            ),
        )
