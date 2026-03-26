from qtrader.governance.simulator_adapter import SimulatorAdapter


def test_simulator_adapter_equity_curve() -> None:
    """Verify that the simulator adapter correctly tracks trade vectors."""
    adapter = SimulatorAdapter(initial_capital=1000.0)

    # 1. Empty equity curve
    df_empty = adapter.get_equity_curve()
    assert df_empty.height == 0  # noqa: S101

    # 2. Add trades
    adapter.process_signal(1, "BTC", "BUY", 100.0, 1.0)
    adapter.process_signal(2, "BTC", "SELL", 105.0, 1.0)

    df_curve = adapter.get_equity_curve()
    assert df_curve.height == 2  # noqa: S101, PLR2004
    assert df_curve["price"][1] == 105.0  # noqa: S101, PLR2004
    assert len(adapter.trades) == 2  # noqa: S101, PLR2004


def test_simulator_adapter_properties() -> None:
    """Verify state isolation and property access."""
    adapter = SimulatorAdapter()
    assert adapter.trades == []  # noqa: S101
