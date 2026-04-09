import json
import re
from pathlib import Path


def fix_python_imports():
    """Systematically migrate local imports to top-level for all 56 violations."""

    def migrate_imports(file_path, local_patterns, top_imports_to_add):
        path = Path(file_path)
        if not path.exists():
            print(f"Skipping {path}: File not found")
            return

        content = path.read_text()
        new_content = content

        # 1. Remove local imports
        removed = False
        for pattern in local_patterns:
            if re.search(pattern, new_content, re.MULTILINE):
                new_content = re.sub(pattern, "", new_content, flags=re.MULTILINE)
                removed = True

        if not removed and top_imports_to_add:
            # Check if top imports already exist
            existing = True
            for imp in top_imports_to_add:
                if imp not in new_content:
                    existing = False
                    break
            if existing:
                print(f"Verified {path}: Imports already correct.")
                return

        # 2. Add top-level imports
        if top_imports_to_add:
            import_block = "\n".join(top_imports_to_add) + "\n"
            lines = new_content.splitlines()
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    insert_idx = i + 1

            lines.insert(insert_idx, import_block)
            new_content = "\n".join(lines).replace("\n\n\n", "\n\n")

        path.write_text(new_content)
        print(f"Migrated imports in {path}")

    # --- API & SERVER ---
    migrate_imports(
        "qtrader/api/server.py",
        [
            r"^\s*from decimal import Decimal\n?",
            r"^\s*from qtrader\.api\.router import get_sim_engine, start_simulation\n?",
            r"^\s*from qtrader\.api\.router import stop_simulation\n?",
            r"^\s*from qtrader\.core\.events import EventType, SystemEvent, SystemPayload\n?",
        ],
        [
            "from decimal import Decimal",
            "from qtrader.core.events import EventType, SystemEvent, SystemPayload",
            "from qtrader.api.router import get_sim_engine, start_simulation, stop_simulation",
        ],
    )
    migrate_imports(
        "qtrader/api/router.py",
        [r"^\s*from qtrader\.core\.db import DBClient\n?"],
        ["from qtrader.core.db import DBClient"],
    )

    # --- ANALYTICS ---
    migrate_imports(
        "qtrader/analytics/forensic_tracer.py",
        [r"^\s*from qtrader\.core\.config import settings\n?"],
        ["from qtrader.core.config import settings"],
    )
    migrate_imports(
        "qtrader/analytics/session_analyzer.py",
        [r"^\s*from collections import defaultdict\n?"],
        ["from collections import defaultdict"],
    )

    # --- ALPHA ---
    migrate_imports("qtrader/alpha/base.py", [r"^\s*import logging\n?"], ["import logging"])
    migrate_imports(
        "qtrader/alpha/mocks/low_latency_alpha.py", [r"^\s*import random\n?"], ["import random"]
    )

    # --- COMPLIANCE ---
    migrate_imports(
        "qtrader/compliance/surveillance_engine.py",
        [r"^\s*from collections import defaultdict\n?"],
        ["from collections import defaultdict"],
    )

    # --- FEATURES ---
    migrate_imports(
        "qtrader/features/registry.py",
        [
            r"^\s*from qtrader\.features\.factors\.lagged import LaggedReturn, ReturnVolatility\n?",
            r"^\s*from qtrader\.features\.factors\.technical import .*?\n\s*.*?\n\s*.*?\n\s*.*?\n\s*.*?\n\s*.*?\n\s*\)",
            r"^\s*from qtrader\.features\.factors\.volume import OBV, VWAP, DollarVolume, ForceIndex, VolumeRatio\n?",
        ],
        [
            "from qtrader.features.factors.lagged import LaggedReturn, ReturnVolatility",
            "from qtrader.features.factors.technical import ATR, MACD, ROC, RSI, BollingerBands, MomentumReturn",
            "from qtrader.features.factors.volume import OBV, VWAP, DollarVolume, ForceIndex, VolumeRatio",
        ],
    )
    migrate_imports(
        "qtrader/features/neutralization.py",
        [r"^\s*import numpy as np\n?", r"^\s*from sklearn\.decomposition import PCA\n?"],
        ["import numpy as np", "from sklearn.decomposition import PCA"],
    )
    migrate_imports("qtrader/features/store.py", [r"^\s*import duckdb\n?"], ["import duckdb"])

    # --- EXECUTION ---
    migrate_imports(
        "qtrader/execution/reconciliation_engine.py",
        [
            r"^\s*from qtrader\.core\.events import SystemEvent\n?",
            r"^\s*from datetime import datetime\n?",
            r"^\s*from qtrader\.core\.state_store import Position\n?",
        ],
        ["from datetime import datetime", "from qtrader.core.state_store import Position"],
    )
    migrate_imports(
        "qtrader/execution/shadow_engine.py",
        [
            r"^\s*from qtrader\.execution\.trade_logger import TradeLogger\n?",
            r"^\s*from qtrader\.core\.types import SystemEvent\n?",
        ],
        [
            "from qtrader.execution.trade_logger import TradeLogger",
            "from qtrader.core.events import SystemEvent",
        ],
    )
    migrate_imports(
        "qtrader/execution/paper_engine.py",
        [r"^\s*from qtrader\.core\.events import MarketEvent, MarketPayload\n?"],
        ["from qtrader.core.events import MarketEvent, MarketPayload"],
    )
    migrate_imports(
        "qtrader/execution/brokers/coinbase.py",
        [
            r"^\s*from collections import namedtuple\n?",
            r"^\s*from qtrader\.core\.events import EventType\n?",
        ],
        ["from collections import namedtuple"],
    )
    migrate_imports("qtrader/execution/algos/pov.py", [r"^\s*import time\n?"], ["import time"])
    migrate_imports(
        "qtrader/execution/core/fill_probability.py", [r"^\s*import logging\n?"], ["import logging"]
    )
    migrate_imports(
        "qtrader/execution/rl/reward.py", [r"^\s*import logging\n?"], ["import logging"]
    )
    migrate_imports(
        "qtrader/execution/routing/cost_model.py", [r"^\s*import logging\n?"], ["import logging"]
    )
    migrate_imports(
        "qtrader/execution/routing/liquidity_model.py",
        [r"^\s*import logging\n?"],
        ["import logging"],
    )
    migrate_imports(
        "qtrader/execution/strategy/scheduler.py", [r"^\s*import logging\n?"], ["import logging"]
    )
    migrate_imports(
        "qtrader/execution/strategy/slicing.py", [r"^\s*import logging\n?"], ["import logging"]
    )
    migrate_imports(
        "qtrader/execution/pre_trade_risk.py",
        [
            r"^\s*from qtrader_core import Account as RustAccount\n?",
            r"^\s*from qtrader_core import Order as RustOrder\n?",
            r"^\s*from qtrader_core import OrderType as RustOrderType\n?",
            r"^\s*from qtrader_core import Side as RustSide\n?",
        ],
        [
            "try:",
            "    from qtrader_core import Account as RustAccount, Order as RustOrder, OrderType as RustOrderType, Side as RustSide",
            "except ImportError:",
            "    HAS_RUST_CORE = False",
        ],
    )

    # --- MICROSTRUCTURE ---
    ms_files = [
        "hidden_liquidity.py",
        "imbalance.py",
        "microprice.py",
        "queue_model.py",
        "spread_model.py",
        "toxic_flow.py",
    ]
    for msf in ms_files:
        migrate_imports(
            f"qtrader/execution/microstructure/{msf}",
            [r"^\s*import logging\n?"],
            ["import logging"],
        )

    # --- CORE ---
    migrate_imports("qtrader/core/fail_fast_engine.py", [r"^\s*import sys\n?"], ["import sys"])
    migrate_imports(
        "qtrader/core/pre_execution_validator.py",
        [r"^\s*from datetime import datetime, timezone\n?"],
        ["from datetime import datetime, timezone"],
    )
    migrate_imports("qtrader/data/duckdb_client.py", [r"^\s*import os\n?"], ["import os"])

    # --- STRATEGY ---
    migrate_imports(
        "qtrader/strategy/base.py",
        [r"^\s*from qtrader\.core\.events import OrderPayload\n?"],
        ["from qtrader.core.events import OrderPayload"],
    )

    # --- TESTS ---
    migrate_imports(
        "tests/unit/core/test_config.py",
        [
            r"^\s*from qtrader\.core\.config import Config as cfg1\n?",
            r"^\s*from qtrader\.core\.config import settings as cfg2\n?",
        ],
        ["from qtrader.core.config import Config as cfg1, settings as cfg2"],
    )
    migrate_imports(
        "tests/unit/core/test_event_store_distributed.py", [r"^\s*import time\n?"], ["import time"]
    )
    migrate_imports(
        "tests/unit/core/test_execution_guard.py", [r"^\s*import json\n?"], ["import json"]
    )
    migrate_imports(
        "tests/unit/data/test_datalake.py",
        [r"^\s*from datetime import datetime\n?"],
        ["from datetime import datetime"],
    )


def fix_notebook_imports():
    """Fix local imports in 06_Strategy_Lab.ipynb."""
    path = Path("notebooks/trader/06_Strategy_Lab.ipynb")
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        nb_data = json.load(f)
    modified = False
    for cell in nb_data.get("cells", []):
        if cell.get("cell_type") == "code":
            source = cell.get("source")
            source_str = "".join(source) if isinstance(source, list) else source
            if (
                "def run_ml_filtered_strategy" in source_str
                and "    import polars as pl" in source_str
            ):
                new_source = source_str.replace("    import polars as pl\n", "")
                if "import polars as pl" not in new_source.splitlines()[0]:
                    new_source = "import polars as pl\n" + new_source
                cell["source"] = new_source
                modified = True
    if modified:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(nb_data, f, indent=1)
        print(f"Updated {path}")


if __name__ == "__main__":
    print("Starting QTrader Institutional Compliance Reconciliation...")
    fix_python_imports()
    fix_notebook_imports()
    print("Reconciliation Complete.")
