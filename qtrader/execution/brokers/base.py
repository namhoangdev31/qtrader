from typing import Any, Protocol, runtime_checkable

from qtrader.core.events import FillEvent, OrderEvent
from qtrader.security.order_signing import OrderSigner, SignedOrder


@runtime_checkable
class BrokerAdapter(Protocol):
    order_signer: OrderSigner | None

    async def submit_order(self, order: OrderEvent) -> str: ...

    async def cancel_order(self, order_id: str) -> bool: ...

    async def get_fills(self, order_id: str) -> list[FillEvent]: ...

    async def get_balance(self) -> dict: ...

    def sign_order(self, order_data: dict[str, Any]) -> SignedOrder | None:
        if self.order_signer:
            return self.order_signer.sign_order(order_data)
        return None

    def verify_order(self, signed_order: SignedOrder) -> tuple[bool, str]:
        if self.order_signer:
            return self.order_signer.verify_order(signed_order)
        return (True, "No signer configured")
