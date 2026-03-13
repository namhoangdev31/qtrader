import inspect

import pytest

from qtrader.execution.brokers.binance import BinanceBrokerAdapter
from qtrader.execution.brokers.coinbase import CoinbaseBrokerAdapter


def _assert_signature(fn, expected_params: list[str]) -> None:
    params = list(inspect.signature(fn).parameters.keys())
    assert params == expected_params


def test_broker_adapter_signatures() -> None:
    # Protocol: submit_order(self, order), cancel_order(self, order_id), get_fills(self, order_id), get_balance(self)
    _assert_signature(BinanceBrokerAdapter.submit_order, ["self", "order"])
    _assert_signature(BinanceBrokerAdapter.cancel_order, ["self", "order_id"])
    _assert_signature(BinanceBrokerAdapter.get_fills, ["self", "order_id"])
    _assert_signature(BinanceBrokerAdapter.get_balance, ["self"])

    _assert_signature(CoinbaseBrokerAdapter.submit_order, ["self", "order"])
    _assert_signature(CoinbaseBrokerAdapter.cancel_order, ["self", "order_id"])
    _assert_signature(CoinbaseBrokerAdapter.get_fills, ["self", "order_id"])
    _assert_signature(CoinbaseBrokerAdapter.get_balance, ["self"])


@pytest.mark.asyncio
async def test_binance_safe_calls_without_mapping() -> None:
    # These should not crash even when order_id was not submitted (missing symbol mapping).
    adapter = BinanceBrokerAdapter(api_key="", api_secret="", testnet=True)
    assert await adapter.cancel_order("unknown") is False
    assert await adapter.get_fills("unknown") == []
