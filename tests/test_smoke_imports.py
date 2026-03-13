import qtrader.core.bus  # noqa: F401
import qtrader.core.event  # noqa: F401
import qtrader.data.duckdb_client  # noqa: F401
import qtrader.execution.brokers.base  # noqa: F401
import qtrader.execution.brokers.binance  # noqa: F401
import qtrader.execution.brokers.coinbase  # noqa: F401
import qtrader.execution.oms  # noqa: F401
import qtrader.execution.sor  # noqa: F401
import qtrader.ml.registry  # noqa: F401


def test_import_core_modules() -> None:
    # Imports happen at module load; test is a simple smoke.
    assert True
