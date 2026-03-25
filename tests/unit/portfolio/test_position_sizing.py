from qtrader.portfolio.position_sizing import PositionSizer

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
TOLERANCE = 1e-6
F_MAX_TEST = 0.5


def test_kelly_fraction_basic() -> None:
    """Verify Kelly fraction for standard win/loss profiles."""
    # Case 1: p=0.6, b=1 -> f = (0.6(2) - 1) / 1 = 0.2
    expected_c1 = 0.2
    assert abs(PositionSizer.compute_kelly_fraction(0.6, 1.0) - expected_c1) < TOLERANCE

    # Case 2: p=0.5, b=2 -> f = (0.5(3) - 1) / 2 = 0.25
    expected_c2 = 0.25
    assert abs(PositionSizer.compute_kelly_fraction(0.5, 2.0) - expected_c2) < TOLERANCE


def test_kelly_fraction_caps() -> None:
    """Verify f_max constraint."""
    # p=0.9, b=2 -> f = (0.9(3) - 1) / 2 = 1.7 / 2 = 0.85
    # Cap at 0.5
    assert PositionSizer.compute_kelly_fraction(0.9, 2.0, f_max=F_MAX_TEST) == F_MAX_TEST


def test_kelly_fraction_negative_edge() -> None:
    """Verify f=0 for negative expected values."""
    # p=0.4, b=1 -> f = (0.4(2) - 1) / 1 = -0.2 -> 0.0
    assert PositionSizer.compute_kelly_fraction(0.4, 1.0) == 0.0

    # p=0.2, b=2 -> f = (0.2(3) - 1) / 2 = -0.4 / 2 = -0.2 -> 0.0
    assert PositionSizer.compute_kelly_fraction(0.2, 2.0) == 0.0


def test_kelly_fraction_edge_cases() -> None:
    """Verify handling of zeros."""
    # Zero win_loss_ratio
    assert PositionSizer.compute_kelly_fraction(0.6, 0.0) == 0.0

    # Zero win_prob
    assert PositionSizer.compute_kelly_fraction(0.0, 1.0) == 0.0

    # Negative win_prob (invalid but handled)
    assert PositionSizer.compute_kelly_fraction(-0.1, 1.0) == 0.0
