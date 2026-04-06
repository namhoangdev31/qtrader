import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from qtrader.analytics.session_analyzer import SessionAnalyzer

@pytest.mark.asyncio
async def test_session_analyzer_no_trades():
    analyzer = SessionAnalyzer()
    
    with patch("qtrader.core.db.DBClient.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [] # No fills
        
        report = await analyzer.analyze_session("test-id", "2024-01-01T00:00:00Z")
        
        assert report["status"] == "NO_TRADES"
        assert "No trades executed" in report["summary"]

@pytest.mark.asyncio
async def test_session_analyzer_basic_pnl():
    analyzer = SessionAnalyzer()
    
    # Mock data
    mock_fills = [
        {"symbol": "BTC-USD", "side": "BUY", "quantity": 1.0, "price": 50000.0, "commission": 10.0, "timestamp": datetime(2024, 1, 1, 10, 0)},
        {"symbol": "BTC-USD", "side": "SELL", "quantity": 1.0, "price": 51000.0, "commission": 10.0, "timestamp": datetime(2024, 1, 1, 11, 0)},
    ]
    mock_thinking = [
        {"symbol": "BTC-USD", "action": "BUY", "confidence": 0.9, "thinking": "Long signal", "timestamp": datetime(2024, 1, 1, 9, 59)},
    ]
    mock_pnl = [
        {"total_equity": 100000.0, "timestamp": datetime(2024, 1, 1, 9, 0)},
        {"total_equity": 100980.0, "timestamp": datetime(2024, 1, 1, 12, 0)},
    ]

    async def side_effect(query, *args):
        if "fills" in query: return mock_fills
        if "ai_thinking_logs" in query: return mock_thinking
        if "pnl_snapshots" in query: return mock_pnl
        return []

    with patch("qtrader.core.db.DBClient.fetch", side_effect=side_effect):
        report = await analyzer.analyze_session("test-id", "2024-01-01T00:00:00Z")
        
        metrics = report["metrics"]
        assert metrics["total_trades"] == 2
        assert metrics["win_count"] == 1
        assert metrics["total_pnl"] == 980.0 # (51000-50000) - 20 commission
        assert metrics["total_gross_pnl"] == 1000.0 # (51000-50000)
        assert metrics["avg_ai_confidence"] == 0.9
        assert "Session ended in profit." in report["highlights"]
