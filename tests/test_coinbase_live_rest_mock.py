
import re

import pytest
from aioresponses import aioresponses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from qtrader.core.event import OrderEvent
from qtrader.execution.brokers.coinbase import CoinbaseBrokerAdapter


def _gen_ec_private_key_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.mark.asyncio
async def test_coinbase_live_submit_cancel_balance_and_fills_mocked() -> None:
    pem = _gen_ec_private_key_pem()
    adapter = CoinbaseBrokerAdapter(
        simulate=False,
        rest_base="https://api.coinbase.com",
        key_name="organizations/x/apiKeys/y",
        private_key_pem=pem,
        max_retries=0,
    )

    order = OrderEvent(symbol="BTC-USD", order_type="MARKET", quantity=1.0, side="BUY", price=None)

    with aioresponses() as m:
        m.post(
            "https://api.coinbase.com/api/v3/brokerage/orders",
            payload={"success": True, "success_response": {"order_id": "OID1"}},
        )
        m.post(
            "https://api.coinbase.com/api/v3/brokerage/orders/batch_cancel",
            payload={"results": [{"order_id": "OID1", "success": True}]},
        )
        m.get(
            "https://api.coinbase.com/api/v3/brokerage/accounts",
            payload={
                "accounts": [
                    {"currency": "USDT", "available_balance": {"value": "10.5"}},
                    {"currency": "BTC", "available_balance": {"value": "0.1"}},
                ]
            },
        )
        fills_url = "https://api.coinbase.com/api/v3/brokerage/orders/historical/fills"
        m.get(
            re.compile(re.escape(fills_url) + ".*"),
            payload={
                "fills": [
                    {
                        "order_id": "OID1",
                        "trade_id": "T1",
                        "product_id": "BTC-USD",
                        "side": "BUY",
                        "size": "1.0",
                        "price": "100.0",
                        "commission": "0.1",
                    }
                ]
            },
        )

        oid = await adapter.submit_order(order)
        assert oid == "OID1"
        assert await adapter.cancel_order(oid) is True
        bal = await adapter.get_balance()
        assert bal["USDT"] == 10.5
        fills = await adapter.get_fills(oid)
        assert len(fills) == 1
        assert fills[0].fill_id == "T1"

    await adapter.close()
