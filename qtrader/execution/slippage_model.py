import logging
from decimal import Decimal
from typing import Any
from qtrader_core import SlippageModel as RustSlippageModel

logger = logging.getLogger(__name__)


class SlippageModel(RustSlippageModel):
    def __init__(
        self,
        temporary_impact_factor: Decimal = Decimal("0.1"),
        permanent_impact_factor: Decimal = Decimal("0.05"),
        volatility_factor: Decimal = Decimal("2.5"),
    ) -> None:
        super().__init__(
            temporary_impact=float(temporary_impact_factor),
            permanent_impact=float(permanent_impact_factor),
            volatility_factor=float(volatility_factor),
        )

    async def compute_slippage(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        orderbook: dict[str, Any],
        volatility: Decimal,
    ) -> Decimal:
        try:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            if not bids or not asks:
                return Decimal("0")
            mid_price = (float(bids[0][0]) + float(asks[0][0])) / 2.0
            total_volume = sum((float(l[1]) for l in bids)) + sum((float(l[1]) for l in asks))
            slippage = super().compute_slippage(
                side_is_buy=side.upper() == "BUY",
                quantity=float(quantity),
                mid_price=mid_price,
                total_volume=total_volume,
                volatility=float(volatility),
            )
            return Decimal(str(slippage))
        except Exception as e:
            logger.error(f"Rust slippage model failure: {e}")
            return Decimal("0.01")
