import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.core.events import EventType
from qtrader.core.exceptions import SystemHalt
from qtrader.core.runtime_gatekeeper import RuntimeGatekeeper


@pytest.fixture
def temp_logs(tmp_path):
    halt_log = tmp_path / "halt_log.json"
    monitoring_map = tmp_path / "monitoring_map.json"
    return str(halt_log), str(monitoring_map)


@pytest.mark.asyncio
async def test_gatekeeper_check_success(temp_logs):
    halt_path, map_path = temp_logs
    gatekeeper = RuntimeGatekeeper(halt_log_path=halt_path, monitoring_map_path=map_path)

    with patch("qtrader.core.runtime_gatekeeper.enforcement_engine") as mock_engine:
        mock_engine.validate_pre_execution = AsyncMock()

        await gatekeeper.check({"stage": "test_stage", "trace_id": "test_trace"})

        assert mock_engine.validate_pre_execution.called
        assert gatekeeper.violations_detected == 0

        # Verify monitoring map
        with open(map_path) as f:
            data = json.load(f)
            assert data["stage_metrics"]["test_stage"]["checks"] == 1
            assert data["stage_metrics"]["test_stage"]["violations"] == 0


@pytest.mark.asyncio
async def test_gatekeeper_check_violation(temp_logs):
    halt_path, map_path = temp_logs
    gatekeeper = RuntimeGatekeeper(halt_log_path=halt_path, monitoring_map_path=map_path)

    with patch("qtrader.core.runtime_gatekeeper.enforcement_engine") as mock_engine:
        mock_engine.validate_pre_execution = AsyncMock(side_effect=ValueError("Trace missing"))

        with pytest.raises(SystemHalt, match="Trace missing"):
            await gatekeeper.check({"stage": "critical_stage"})

        assert gatekeeper.violations_detected == 1
        assert gatekeeper.halt_count == 1

        # Verify halt log
        with open(halt_path) as f:
            logs = json.load(f)
            assert len(logs) == 1
            assert "Trace missing" in logs[0]["reason"]

        # Verify monitoring map
        with open(map_path) as f:
            data = json.load(f)
            assert data["stage_metrics"]["critical_stage"]["violations"] == 1
            assert data["halt_count"] == 1


@pytest.mark.asyncio
async def test_gatekeeper_check_event(temp_logs):
    halt_path, map_path = temp_logs
    gatekeeper = RuntimeGatekeeper(halt_log_path=halt_path, monitoring_map_path=map_path)

    event = MagicMock()
    event.event_type.name = "MARKET_DATA"

    with patch("qtrader.core.runtime_gatekeeper.enforcement_engine") as mock_engine:
        mock_engine.validate_event = AsyncMock()

        await gatekeeper.check_event(event)

        assert mock_engine.validate_event.called
        assert gatekeeper.violations_detected == 0
