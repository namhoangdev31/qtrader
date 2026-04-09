import json
import re
from pathlib import Path


def migrate_imports(file_path, local_patterns, top_imports_to_add):
    """
    Hàm bổ trợ để di chuyển import từ local lên top-level.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"⏩ Skipping {path}: File not found")
        return

    content = path.read_text()
    new_content = content

    # 1. Xóa các local imports dựa trên patterns
    removed = False
    for pattern in local_patterns:
        if re.search(pattern, new_content, re.MULTILINE):
            new_content = re.sub(pattern, "", new_content, flags=re.MULTILINE)
            removed = True

    # 2. Kiểm tra nếu import đã tồn tại ở top-level thì không thêm trùng
    top_imports_to_add = [imp for imp in top_imports_to_add if imp not in new_content]

    if not removed and not top_imports_to_add:
        print(f"✅ Verified {path}: Imports already correct.")
        return

    # 3. Thêm vào top-level (sau các dòng import hiện có hoặc ở đầu file)
    if top_imports_to_add:
        lines = new_content.splitlines()
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")):
                insert_idx = i + 1

        import_block = "\n".join(top_imports_to_add)
        if insert_idx == 0:
            new_content = import_block + "\n\n" + new_content
        else:
            lines.insert(insert_idx, import_block)
            new_content = "\n".join(lines)

    # Clean up: Xóa khoảng trắng thừa (3 dòng trống liên tiếp)
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)

    path.write_text(new_content.strip() + "\n")
    print(f"🚀 Migrated imports in {path}")


def fix_python_imports():
    """Systematically migrate local imports for QTrader modules."""

    # Định nghĩa danh sách các task để code gọn hơn
    tasks = [
        # --- API & SERVER ---
        {
            "path": "qtrader/api/server.py",
            "patterns": [
                r"^\s*from decimal import Decimal\n?",
                r"^\s*from qtrader\.api\.router import.*\n?",
                r"^\s*from qtrader\.core\.events import.*\n?",
            ],
            "imports": [
                "from decimal import Decimal",
                "from qtrader.core.events import EventType, SystemEvent, SystemPayload",
                "from qtrader.api.router import get_sim_engine, start_simulation, stop_simulation",
            ],
        },
        {
            "path": "qtrader/api/router.py",
            "patterns": [r"^\s*from qtrader\.core\.db import DBClient\n?"],
            "imports": ["from qtrader.core.db import DBClient"],
        },
        # --- FEATURES ---
        {
            "path": "qtrader/features/registry.py",
            "patterns": [r"^\s*from qtrader\.features\.factors.*import.*\n?"],
            "imports": [
                "from qtrader.features.factors.lagged import LaggedReturn, ReturnVolatility",
                "from qtrader.features.factors.technical import ATR, MACD, ROC, RSI, BollingerBands, MomentumReturn",
                "from qtrader.features.factors.volume import OBV, VWAP, DollarVolume, ForceIndex, VolumeRatio",
            ],
        },
        # --- EXECUTION & RUST CORE ---
        {
            "path": "qtrader/execution/pre_trade_risk.py",
            "patterns": [r"^\s*from qtrader_core import.*\n?"],
            "imports": [
                "try:",
                "    from qtrader_core import Account as RustAccount, Order as RustOrder, OrderType as RustOrderType, Side as RustSide",
                "except ImportError:",
                "    HAS_RUST_CORE = False",
            ],
        },
        # --- ANALYTICS, ALPHA, COMPLIANCE ---
        {
            "path": "qtrader/analytics/forensic_tracer.py",
            "patterns": [r"import settings"],
            "imports": ["from qtrader.core.config import settings"],
        },
        {
            "path": "qtrader/alpha/base.py",
            "patterns": [r"import logging"],
            "imports": ["import logging"],
        },
        {
            "path": "qtrader/features/store.py",
            "patterns": [r"import duckdb"],
            "imports": ["import duckdb"],
        },
    ]

    # Chạy các task đơn lẻ
    for task in tasks:
        migrate_imports(task["path"], task["patterns"], task["imports"])

    # Xử lý hàng loạt cho Microstructure
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


def fix_notebook_imports():
    """Sửa lỗi local imports trong file Jupyter Notebook."""
    path = Path("notebooks/trader/06_Strategy_Lab.ipynb")
    if not path.exists():
        return

    nb_data = json.loads(path.read_text(encoding="utf-8"))
    modified = False

    for cell in nb_data.get("cells", []):
        if cell.get("cell_type") == "code":
            source = "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]

            if "import polars as pl" in source and ("def " in source or "class " in source):
                # Xóa bản cũ trong function và đưa lên đầu cell
                new_source = re.sub(r"^\s*import polars as pl\n?", "", source, flags=re.MULTILINE)
                cell["source"] = "import polars as pl\n" + new_source.strip()
                modified = True

    if modified:
        path.write_text(json.dumps(nb_data, indent=1), encoding="utf-8")
        print(f"✨ Updated Notebook: {path}")


if __name__ == "__main__":
    print("🛠 Starting QTrader Codebase Reconciliation...")
    fix_python_imports()
    fix_notebook_imports()
    print("✅ Finished.")
