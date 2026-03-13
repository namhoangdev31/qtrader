import re

import pytest
from aioresponses import aioresponses

from qtrader.execution.brokers.binance import BinanceBrokerAdapter


@pytest.mark.asyncio
async def test_binance_get_fills_parses_mytrades() -> None:
    adapter = BinanceBrokerAdapter(api_key="k", api_secret="s", testnet=True)
    adapter._order_symbol["123"] = "BTCUSDT"

    url = f"{adapter.base_url}/api/v3/myTrades"
    payload = [
        {
            "id": 1,
            "orderId": 123,
            "price": "100.0",
            "qty": "0.5",
            "commission": "0.01",
            "isBuyer": True,
        },
        {
            "id": 2,
            "orderId": 123,
            "price": "101.0",
            "qty": "0.5",
            "commission": "0.01",
            "isBuyer": False,
        },
    ]

    with aioresponses() as m:
        m.get(re.compile(re.escape(url) + ".*"), payload=payload)
        fills = await adapter.get_fills("123")

    assert len(fills) == 2
    assert fills[0].side in ("BUY", "SELL")
    assert fills[0].commission == 0.01

    await adapter.close()
