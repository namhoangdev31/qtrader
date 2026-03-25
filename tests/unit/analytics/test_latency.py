"""Unit tests for qtrader.analytics.latency."""

from __future__ import annotations

import polars as pl
import pytest

from qtrader.analytics.latency import LatencyAnalyzer

# ──────────────────────────────────────────────
# Constants (PLR2004)
# ──────────────────────────────────────────────
T_MARKET: float = 0.0
T_SIGNAL: float = 10.0
T_ORDER: float  = 25.0
T_FILL: float   = 80.0

L_ALPHA_EXPECTED: float = 10.0   # t_signal - t_market
L_EXEC_EXPECTED: float  = 15.0   # t_order  - t_signal
L_FILL_EXPECTED: float  = 55.0   # t_fill   - t_order
L_TOTAL_EXPECTED: float = 80.0   # t_fill   - t_market

SLA_MS: float = 100.0
OVER_SLA_FILL: float = 150.0     # t_fill that pushes total > 100ms


# ──────────────────────────────────────────────
# Scalar tests
# ──────────────────────────────────────────────

def test_scalar_breakdown_values() -> None:
    """Verify each stage latency matches the expected math."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute(T_MARKET, T_SIGNAL, T_ORDER, T_FILL)

    assert result.l_alpha == L_ALPHA_EXPECTED
    assert result.l_exec  == L_EXEC_EXPECTED
    assert result.l_fill  == L_FILL_EXPECTED
    assert result.l_total == L_TOTAL_EXPECTED


def test_components_sum_equals_total() -> None:
    """Key acceptance criterion: l_alpha + l_exec + l_fill == l_total."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute(T_MARKET, T_SIGNAL, T_ORDER, T_FILL)

    assert result.components_sum == pytest.approx(result.l_total)


def test_within_sla_true() -> None:
    """80ms total latency is within the 100ms SLA."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute(T_MARKET, T_SIGNAL, T_ORDER, T_FILL)

    assert result.within_sla is True


def test_within_sla_false() -> None:
    """150ms total latency breaches the 100ms SLA."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute(T_MARKET, T_SIGNAL, T_ORDER, OVER_SLA_FILL)

    assert result.within_sla is False


def test_zero_latency_stages() -> None:
    """All timestamps equal → all stages measure 0ms."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute(T_MARKET, T_MARKET, T_MARKET, T_MARKET)

    assert result.l_alpha == 0.0
    assert result.l_exec  == 0.0
    assert result.l_fill  == 0.0
    assert result.l_total == 0.0
    assert result.components_sum == pytest.approx(result.l_total)


def test_non_monotonic_timestamps_raise() -> None:
    """Non-monotonic timestamps must raise ValueError."""
    analyzer = LatencyAnalyzer()
    with pytest.raises(ValueError, match="monotonically"):
        analyzer.compute(T_SIGNAL, T_MARKET, T_ORDER, T_FILL)


# ──────────────────────────────────────────────
# Batch (Polars) tests
# ──────────────────────────────────────────────

def _make_batch() -> pl.DataFrame:
    """Helper: two rows — one within SLA, one breaching it."""
    return pl.DataFrame({
        "t_market": [T_MARKET, T_MARKET],
        "t_signal": [T_SIGNAL, T_SIGNAL],
        "t_order":  [T_ORDER,  T_ORDER],
        "t_fill":   [T_FILL,   OVER_SLA_FILL],
    })


def test_batch_output_columns() -> None:
    """Batch method must produce l_alpha, l_exec, l_fill, l_total, within_sla."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute_batch(_make_batch())

    for col in ("l_alpha", "l_exec", "l_fill", "l_total", "within_sla"):
        assert col in result.columns


def test_batch_sum_equals_total() -> None:
    """Sum of component columns must equal l_total for every row."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute_batch(_make_batch())

    component_sum = (
        result["l_alpha"] + result["l_exec"] + result["l_fill"]
    )
    for computed, total in zip(component_sum.to_list(), result["l_total"].to_list(), strict=True):

        assert computed == pytest.approx(total)


def test_batch_sla_flags() -> None:
    """Row 0 (80ms) should pass SLA; row 1 (150ms) should fail."""
    analyzer = LatencyAnalyzer()
    result = analyzer.compute_batch(_make_batch())

    flags = result["within_sla"].to_list()
    assert flags[0] is True
    assert flags[1] is False


def test_batch_missing_column_raises() -> None:
    """Missing required column must raise ValueError."""
    analyzer = LatencyAnalyzer()
    bad_df = pl.DataFrame({"t_market": [0.0], "t_signal": [10.0]})
    with pytest.raises(ValueError, match="Missing required columns"):
        analyzer.compute_batch(bad_df)


def test_summarize_batch() -> None:
    """summarize_batch must return p50, p90, p99, sla_pass_rate."""
    analyzer = LatencyAnalyzer()
    enriched = analyzer.compute_batch(_make_batch())
    stats = analyzer.summarize_batch(enriched)

    assert "p50" in stats
    assert "p90" in stats
    assert "p99" in stats
    assert "sla_pass_rate" in stats
    assert 0.0 <= stats["sla_pass_rate"] <= 1.0
