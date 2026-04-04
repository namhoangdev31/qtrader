from typing import Any, Protocol, runtime_checkable

from qtrader.core.events import FillEvent, OrderEvent
from qtrader.security.order_signing import OrderSigner, SignedOrder


@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol for connecting to live brokers/exchanges."""

    order_signer: OrderSigner | None

    async def submit_order(self, order: OrderEvent) -> str:
        """Submit order and return broker order ID."""
        ...

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        ...

    async def get_fills(self, order_id: str) -> list[FillEvent]:
        """Fetch fills for a specific order."""
        ...

    async def get_balance(self) -> dict:
        """Fetch account balances."""
        ...

    def sign_order(self, order_data: dict[str, Any]) -> SignedOrder | None:
        """Sign an order payload before submission (Standash §5.3)."""
        if self.order_signer:
            return self.order_signer.sign_order(order_data)
        return None

    def verify_order(self, signed_order: SignedOrder) -> tuple[bool, str]:
        """Verify a signed order's integrity (Standash §5.3)."""
        if self.order_signer:
            return self.order_signer.verify_order(signed_order)
        return True, "No signer configured"
