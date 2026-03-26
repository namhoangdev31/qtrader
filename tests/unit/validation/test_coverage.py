from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import EventType
from qtrader.validation.coverage import CoverageEnforcer

# Test Constants
PACKAGE_NAME = "qtrader.alpha.momentum"


@pytest.mark.asyncio
async def test_coverage_enforcer_compute_success() -> None:
    """Verify coverage appraisal with industrial-grade logic."""
    bus = AsyncMock()
    enforcer = CoverageEnforcer(bus)

    # Coverage Data: Tested 96 lines out of 100
    coverage_data = {"tested_lines": 96, "total_lines": 100, "missing_lines": [4, 5, 22, 23]}

    event = await enforcer.enforce_coverage(PACKAGE_NAME, coverage_data, threshold=95.0)

    # 1. Validation of Coverage Score
    assert event is not None  # noqa: S101
    assert event.payload.coverage_pct == 96.0  # noqa: S101, PLR2004
    assert event.payload.uncovered_lines == [4, 5, 22, 23]  # noqa: S101
    assert event.payload.metadata["is_passing"]  # noqa: S101

    # 2. Validation of Event Bus Publish
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.COVERAGE_REPORT  # noqa: S101


@pytest.mark.asyncio
async def test_coverage_enforcer_violation() -> None:
    """Verify that a coverage violation triggers industrial error logging."""
    bus = AsyncMock()
    enforcer = CoverageEnforcer(bus)

    # Coverage Data: Tested 80 lines out of 100
    coverage_data = {"tested_lines": 80, "total_lines": 100, "missing_lines": list(range(1, 21))}

    event = await enforcer.enforce_coverage(PACKAGE_NAME, coverage_data, threshold=95.0)

    # 1. Validation of Coverage Violation (Metadata should show is_passing=False)
    assert event is not None  # noqa: S101
    assert event.payload.coverage_pct == 80.0  # noqa: S101, PLR2004
    assert not event.payload.metadata["is_passing"]  # noqa: S101

    # 2. Status Broadcast
    assert bus.publish.called  # noqa: S101


@pytest.mark.asyncio
async def test_coverage_enforcer_package_failure() -> None:
    """Verify industrial error recovery from malformed or missing metadata."""
    bus = AsyncMock()
    enforcer = CoverageEnforcer(bus)

    # Malformed Data: Zero lines total
    coverage_data = {"tested_lines": 0, "total_lines": 0}

    event = await enforcer.enforce_coverage(PACKAGE_NAME, coverage_data)

    assert event is None  # noqa: S101
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.COVERAGE_ERROR  # noqa: S101
    assert " zero lines" in str(bus.publish.call_args)  # noqa: S101
