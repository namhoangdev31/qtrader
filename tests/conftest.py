import sys
import os
from pathlib import Path

# Add the root directory to sys.path
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

# Add the qtrader/qtrader directory to sys.path to support 'from bot.config import ...'
package_dir = root_dir / "qtrader"
sys.path.append(str(package_dir))
