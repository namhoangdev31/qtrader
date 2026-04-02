from unittest.mock import MagicMock

import pytest

from qtrader.api.api import QTraderAPI


def test_api_initialization():
    api = QTraderAPI(host="localhost", port=8000)
    assert api.host == "localhost"
    assert api.port == 8000

def test_api_get_status():
    api = QTraderAPI()
    api.engine = MagicMock()
    api.engine.is_running.return_value = True
    
    status = api.get_status()
    assert status["running"] is True
