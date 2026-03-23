import pytest
import polars as pl
from qtrader.analytics.performance import PerformanceAnalytics

def test_performance_analytics_init():
    analytics = PerformanceAnalytics(risk_free_rate=0.02)
    assert analytics.risk_free_rate == 0.02

def test_performance_analytics_calculate_metrics():
    analytics = PerformanceAnalytics()
    # Simple equity curve
    equity = pl.DataFrame({
        "timestamp": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "equity": [1000.0, 1050.0, 1020.0]
    })
    
    metrics = analytics.calculate_metrics(equity, initial_capital=1000.0)
    assert "total_return" in metrics
    # return = (1020 - 1000) / 1000 = 0.02
    assert float(metrics["total_return"]) == pytest.approx(0.02)
    
    assert "peak_equity" in metrics
    assert float(metrics["peak_equity"]) == 1050.0
    
    assert "max_drawdown" in metrics
    # DD from 1050 to 1020 = 30 / 1050 = 0.02857
    assert float(metrics["max_drawdown"]) > 0.0

def test_performance_analytics_calculate_metrics_empty():
    analytics = PerformanceAnalytics()
    equity = pl.DataFrame({"timestamp": [], "equity": []})
    metrics = analytics.calculate_metrics(equity, 1000.0)
    assert metrics["total_return"] == 0.0
