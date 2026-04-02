"""
Level 2 Critical Tests: Portfolio Allocation
Covers: HRPOptimizer, CVaROptimizer
Focus: weights sum to 1, all long-only non-negative, low-risk asset gets higher weight,
concentration risk, empty input, and numerical stability.
"""
import numpy as np
import polars as pl
import pytest

from qtrader.portfolio.hrp import CVaROptimizer, HRPOptimizer


# Helper: generate T×N return matrix
def make_returns(t=100, n=3, seed=42):
    rng = np.random.default_rng(seed)
    data = {f"A{i}": rng.normal(0, 0.01, t).tolist() for i in range(n)}
    return pl.DataFrame(data)


def make_returns_with_different_vols(t=200):
    """A has low vol, B has high vol — HRP should weight A more."""
    rng = np.random.default_rng(0)
    return pl.DataFrame({
        "low_vol":  rng.normal(0, 0.005, t).tolist(),
        "high_vol": rng.normal(0, 0.05, t).tolist(),
    })


# ---------------------------------------------------------------------------
# HRPOptimizer
# ---------------------------------------------------------------------------

class TestHRPOptimizer:
    def test_weights_sum_to_one(self):
        hrp = HRPOptimizer()
        returns = make_returns()
        w = hrp.optimize(returns)
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_all_weights_non_negative(self):
        hrp = HRPOptimizer()
        w = hrp.optimize(make_returns())
        assert all(v >= -1e-8 for v in w.values()), "HRP must produce long-only weights"

    def test_symbols_match_columns(self):
        hrp = HRPOptimizer()
        returns = make_returns(n=4)
        w = hrp.optimize(returns)
        assert set(w.keys()) == set(returns.columns)

    def test_low_vol_asset_gets_higher_weight(self):
        """Lower-volatility asset should receive strictly greater allocation."""
        hrp = HRPOptimizer()
        returns = make_returns_with_different_vols()
        w = hrp.optimize(returns)
        assert w["low_vol"] > w["high_vol"], \
            f"Expected low_vol ({w['low_vol']:.4f}) > high_vol ({w['high_vol']:.4f})"

    def test_single_asset_gets_full_weight(self):
        hrp = HRPOptimizer()
        returns = pl.DataFrame({"BTC": [0.01, -0.02, 0.015, 0.005, -0.01] * 10})
        w = hrp.optimize(returns)
        assert w["BTC"] == pytest.approx(1.0, abs=1e-6)

    def test_empty_returns_returns_empty_dict(self):
        hrp = HRPOptimizer()
        assert hrp.optimize(pl.DataFrame()) == {}

    def test_zero_rows_returns_empty_dict(self):
        hrp = HRPOptimizer()
        returns = pl.DataFrame({"A": [], "B": []})
        assert hrp.optimize(returns) == {}

    def test_highly_correlated_assets_no_all_in(self):
        """Two near-perfectly correlated assets should each get ~50% weight."""
        rng = np.random.default_rng(99)
        base = rng.normal(0, 0.01, 200)
        returns = pl.DataFrame({
            "A": base.tolist(),
            "B": (base + rng.normal(0, 1e-6, 200)).tolist(),  # near-perfect correlation
        })
        hrp = HRPOptimizer()
        w = hrp.optimize(returns)
        # Both should be roughly equal
        assert abs(w["A"] - w["B"]) < 0.2, "Near-correlated assets should split weight roughly equally"

    def test_reproducibility(self):
        """Same input → same output (deterministic)."""
        returns = make_returns()
        hrp = HRPOptimizer()
        w1 = hrp.optimize(returns)
        w2 = hrp.optimize(returns)
        for sym in w1:
            assert w1[sym] == pytest.approx(w2[sym], abs=1e-10)


# ---------------------------------------------------------------------------
# CVaROptimizer
# ---------------------------------------------------------------------------

class TestCVaROptimizer:
    def test_weights_sum_to_one(self):
        opt = CVaROptimizer(alpha=0.05, long_only=True)
        w = opt.optimize(make_returns())
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_long_only_non_negative(self):
        opt = CVaROptimizer(long_only=True)
        w = opt.optimize(make_returns())
        assert all(v >= -1e-8 for v in w.values())

    def test_symbols_match_columns(self):
        opt = CVaROptimizer()
        returns = make_returns(n=2)
        w = opt.optimize(returns)
        assert set(w.keys()) == set(returns.columns)

    def test_empty_returns_returns_empty_dict(self):
        opt = CVaROptimizer()
        assert opt.optimize(pl.DataFrame()) == {}

    def test_short_allowed_when_long_only_false(self):
        opt = CVaROptimizer(alpha=0.05, long_only=False)
        returns = make_returns()
        w = opt.optimize(returns)
        # Merely check it doesn't crash and sums to 1
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_cvar_concentrates_on_low_risk_asset(self):
        """Asset with heavily fat tails should get less allocation under CVaR minimisation."""
        rng = np.random.default_rng(7)
        t = 300
        safe   = rng.normal(0, 0.005, t).tolist()
        risky  = np.concatenate([
            rng.normal(0, 0.005, int(t * 0.9)),
            rng.normal(0, 0.15,  int(t * 0.1)),  # 10% fat-tail days
        ]).tolist()
        returns = pl.DataFrame({"safe": safe, "risky": risky})
        opt = CVaROptimizer(alpha=0.05, long_only=True)
        w = opt.optimize(returns)
        assert w["safe"] > w["risky"], \
            f"CVaR should prefer safe asset. safe={w['safe']:.4f}, risky={w['risky']:.4f}"
