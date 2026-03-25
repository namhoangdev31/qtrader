import asyncio
import json
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qtrader.monitoring.api import broadcast_snapshot, router, warroom_service

# Constants for verification
HTTP_OK = 200
INITIAL_NAV = 1000000.0
LOWER_NAV = 950000.0
HIGHER_NAV = 1050000.0
EXPECTED_PNL = 50000.0
EXPECTED_ZERO_PNL = 0.0
SLEEP_DUR = 0.01

# Create a test app
app = FastAPI()
app.include_router(router)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client fixture."""
    with TestClient(app) as test_client:
        yield test_client


def test_api_snapshot(client: TestClient) -> None:
    """Verify /monitoring/snapshot returns valid data."""
    # Ensure some data exists
    warroom_service.aggregator.update_pnl(nav=INITIAL_NAV)
    
    response = client.get("/monitoring/snapshot")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert "pnl" in data
    assert "risk" in data
    assert "latency" in data
    assert data["pnl"]["total"] == EXPECTED_ZERO_PNL


def test_api_health(client: TestClient) -> None:
    """Verify /monitoring/health endpoint."""
    response = client.get("/monitoring/health")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert "status" in data
    assert "queue_size" in data


@pytest.mark.asyncio
async def test_api_websocket() -> None:
    """Verify WebSocket initial connection and broadcast."""
    with TestClient(app) as local_client:
        with local_client.websocket_connect("/monitoring/ws") as websocket:
            # We should immediately receive the initial snapshot upon connection
            response_text = websocket.receive_text()
            data = json.loads(response_text)
            assert "pnl" in data
            
            # Simulate a dashboard update cycle by directly triggering the broadcast callback
            warroom_service.aggregator.update_pnl(nav=HIGHER_NAV)
            snapshot = warroom_service.get_dashboard_snapshot()
            
            # The callback should eventually send data
            broadcast_snapshot(snapshot)
            
            # Allow event loop a moment to process the task
            await asyncio.sleep(SLEEP_DUR)
            
            # Wait for next message pushed to WebSocket
            # Since TestClient websocket is synchronous in its block, we just read
            update_text = websocket.receive_text()
            update_data = json.loads(update_text)
            
            # Initial NAV was 1000000.0, second is 1050000.0 -> PnL is 50000.0
            assert update_data["pnl"]["total"] == EXPECTED_PNL
