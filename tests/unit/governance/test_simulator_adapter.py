from qtrader.governance.simulator_adapter import SimulatorAdapter


def test_simulator_adapter_equity_curve() -> None:
    adapter = SimulatorAdapter(initial_capital=1000.0)
    df_empty = adapter.get_equity_curve()
    assert df_empty.height == 0
    adapter.process_signal(1, "BTC", "BUY", 100.0, 1.0)
    adapter.process_signal(2, "BTC", "SELL", 105.0, 1.0)
    df_curve = adapter.get_equity_curve()
    assert df_curve.height == 2
    assert df_curve["price"][1] == 105.0
    assert len(adapter.trades) == 2


def test_simulator_adapter_properties() -> None:
    adapter = SimulatorAdapter()
    assert adapter.trades == []
