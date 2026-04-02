import asyncio

import pytest

from qtrader.core.error_bus import ErrorBus
from qtrader.core.event import EventType
from qtrader.core.event_bus import EventBus
from qtrader.monitoring.alerting import AlertSystem


@pytest.mark.asyncio
async def test_global_error_alert_system():
    # Setup global bus
    main_bus = EventBus()
    await main_bus.start()
    
    # Initialize components
    alert_system = AlertSystem(main_bus)
    await alert_system.start()
    
    error_bus = ErrorBus(main_bus=main_bus)
    
    # Trigger error
    await error_bus.publish(
        source="TEST_MODULE",
        message="Simulated Database Failure",
        severity="CRITICAL"
    )
    
    # Allow async propagation
    await asyncio.sleep(0.1)
    
    # Validate alert sent
    alerts = alert_system.get_sent_alerts()
    assert len(alerts) == 1
    assert alerts[0].message == "Simulated Database Failure"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].source == "TEST_MODULE"

    # Test that warning does not trigger alert
    await error_bus.publish(
        source="TEST_MODULE",
        message="Simulated Warning",
        severity="WARNING"
    )
    
    await asyncio.sleep(0.1)
    
    # Still 1 alert, warning was skipped
    assert len(alert_system.get_sent_alerts()) == 1

