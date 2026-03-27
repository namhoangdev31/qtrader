import pytest

from qtrader.risk.anomaly_detector import AnomalyDetector


@pytest.fixture
def detector() -> AnomalyDetector:
    """Initialize AnomalyDetector with industrial defaults (3.0 Sigma)."""
    return AnomalyDetector(z_threshold=3.0, history_window=100)


def test_univariate_zscore_spike(detector: AnomalyDetector) -> None:
    """Verify that a large univariate spike (Z > 3) triggers an anomaly."""
    # 1. Prime the history with stable data (30 samples)
    # Window is 100, let's do 110 to trigger pop(0)
    for i in range(110):
        val = 10.0 + (i % 2)  # Mu ~ 10.5, Sigma ~ 0.5
        detector.evaluate_univariate("pnl", val)

    # 2. Z = (25 - 10.5) / 0.5 = 29 >> 3.0
    result = detector.evaluate_univariate("pnl", 25.0)
    assert result["anomaly"] == True  # noqa: S101, E712
    assert result["score"] > 3.0  # noqa: S101, PLR2004


def test_univariate_normal_data(detector: AnomalyDetector) -> None:
    """Verify that stable data remains non-anomalous."""
    for i in range(50):
        detector.evaluate_univariate("latency", 10.0 + (i % 2))

    result = detector.evaluate_univariate("latency", 10.5)
    assert result["anomaly"] == False  # noqa: S101, E712


def test_multivariate_iforest_anomaly(detector: AnomalyDetector) -> None:
    """Verify that the Isolation Forest detects abnormal high-dimensional vectors."""
    # 1. Train on nominal vectors [pnl, latent, signal]
    # Nominal: [high pnl, low latent, high signal]
    for _ in range(120):
        detector.evaluate_multivariate([1000.0, 10.0, 0.9])

    # 2. Trigger Anomaly: [low pnl, high latent, low signal]
    # Vector: [0.0, 500.0, 0.1]
    result = detector.evaluate_multivariate([0.0, 500.0, 0.1])

    assert result["status"] == "ANALYSIS"  # noqa: S101
    assert result["anomaly"] == True  # noqa: S101, E712
    assert result["score"] > 0.0  # noqa: S101


def test_detector_warm_up_phase(detector: AnomalyDetector) -> None:
    """Verify that the detector reports WARM_UP status for small windows."""
    # Univariate (min 30)
    for _ in range(10):
        res = detector.evaluate_univariate("test", 1.0)
        assert res["status"] == "WARM_UP"  # noqa: S101

    # Multivariate (min 100)
    for _ in range(50):
        res = detector.evaluate_multivariate([1.0, 2.0])
        assert res["status"] == "WARM_UP"  # noqa: S101


def test_anomaly_summary_report(detector: AnomalyDetector) -> None:
    """Verify situational awareness report accuracy."""
    # 1. Trigger Univariate Anomaly
    for i in range(110):
        detector.evaluate_univariate("X", 10.0 + (i % 2))
    detector.evaluate_univariate("X", 50.0)

    # 2. Trigger Multivariate Anomaly
    for _ in range(110):
        detector.evaluate_multivariate([10.0, 10.0])
    detector.evaluate_multivariate([500.0, 500.0])

    report = detector.get_anomaly_report()
    assert report["total_anomalies"] == 2  # noqa: S101, PLR2004
    assert report["anomaly_rate"] > 0.0  # noqa: S101
