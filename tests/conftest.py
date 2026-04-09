import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
package_dir = root_dir / "qtrader"
sys.path.append(str(package_dir))


class MockTensor:
    pass


ML_LIBS = {
    "torch": MagicMock(Tensor=MockTensor),
    "torch.nn": MagicMock(),
    "torch.optim": MagicMock(),
    "torch.utils": MagicMock(),
    "torch.utils.data": MagicMock(),
    "xgboost": MagicMock(),
    "catboost": MagicMock(),
    "lightgbm": MagicMock(),
    "ray": MagicMock(),
    "ray.tune": MagicMock(),
    "mlflow": MagicMock(),
    "mlflow.pyfunc": MagicMock(),
}
for lib_name, mock_obj in ML_LIBS.items():
    if lib_name not in sys.modules:
        sys.modules[lib_name] = mock_obj
