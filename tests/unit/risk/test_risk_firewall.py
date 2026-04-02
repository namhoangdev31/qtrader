import pytest

from qtrader.risk.risk_firewall import OrderProposal, PortfolioRiskState, RiskFirewall


@pytest.fixture
def firewall() -> RiskFirewall:
    """Initialize RiskFirewall with industrial defaults (2% VaR, 15% DD)."""
    return RiskFirewall(
        max_var_pct=0.02,
        max_drawdown_pct=0.15,
        max_gross_leverage=1.0,  # Set to 1x for simple test math
    )


@pytest.fixture
def healthy_state() -> PortfolioRiskState:
    """Initial state: 100k equity, no exposure, 16% annualized vol."""
    return PortfolioRiskState(
        equity=100_000.0,
        peak_equity=110_000.0,
        volatility_annual=0.1587,  # ~1% daily vol (15.87 / 15.87)
        total_exposure=0.0,
        positions={},
        is_telemetry_valid=True,
    )


def test_risk_allow_order(firewall: RiskFirewall, healthy_state: PortfolioRiskState) -> None:
    """Verify that a small safe order is ALLOWED."""
    # Order for 1k USD (10 shares at 100)
    order = OrderProposal("AAPL", "BUY", 10.0, 100.0)
    result = firewall.validate_order(order, healthy_state)

    assert result["decision"] == "ALLOW"
    # VaR simulated: 1000 * 1.96 * 0.01 = 19.6 USD. 19.6/100000 = 0.000196
    assert result["projected_var"] == pytest.approx(0.0002)


def test_risk_var_breach(firewall: RiskFirewall, healthy_state: PortfolioRiskState) -> None:
    """Verify that an order with excessive VaR is BLOCKED."""
    # Order for 50k USD. VaR = 50000 * 1.96 * 0.01 = 980 USD.
    # 980 / 100000 = 0.0098 (under 2%)

    # Order for 150k USD. VaR = 150000 * 1.96 * 0.01 = 2940 USD.
    # 2940 / 100000 = 0.0294 (over 2% limit)
    order = OrderProposal("BTC", "BUY", 1.5, 100_000.0)
    result = firewall.validate_order(order, healthy_state)

    assert result["decision"] == "BLOCK"
    assert result["reason"] == "VAR_LIMIT_EXCEEDED"


def test_risk_drawdown_block(firewall: RiskFirewall) -> None:
    """Verify that all orders are BLOCKED when in a hard drawdown state."""
    # Equity = 84k from 100k peak (16% DD > 15% max)
    dd_state = PortfolioRiskState(
        equity=84_000.0,
        peak_equity=100_000.0,
        volatility_annual=0.1,
        total_exposure=0.0,
        positions={},
    )
    order = OrderProposal("EURUSD", "BUY", 100.0, 1.0)
    result = firewall.validate_order(order, dd_state)

    assert result["decision"] == "BLOCK"
    assert result["reason"] == "MAX_DRAWDOWN_EXCEEDED"


def test_risk_leverage_reduction(firewall: RiskFirewall, healthy_state: PortfolioRiskState) -> None:
    """Verify that an order pushing leverage is REDUCED to the limit."""
    # Max Lev = 1.0x. Current exposure = 80k. Equity = 100k.
    # Allowable additional = 20k.
    # Order for 50k (500 shares at 100).
    state = PortfolioRiskState(
        equity=100_000.0,
        peak_equity=100_000.0,
        volatility_annual=0.01,  # Low vol to avoid VaR trigger
        total_exposure=80_000.0,
        positions={"AAPL": 80_000.0},
    )
    order = OrderProposal("TSLA", "BUY", 500.0, 100.0)
    result = firewall.validate_order(order, state)

    assert result["decision"] == "REDUCE"
    assert result["allowed_size"] == 200.0


def test_risk_failsafe_mode(firewall: RiskFirewall, healthy_state: PortfolioRiskState) -> None:
    """Verify that stale telemetry triggers a terminal FAIL-SAFE BLOCK."""
    stale_state = PortfolioRiskState(
        equity=100_000.0,
        peak_equity=100_000.0,
        volatility_annual=0.1,
        total_exposure=0.0,
        positions={},
        is_telemetry_valid=False,
    )
    order = OrderProposal("SPY", "BUY", 10.0, 400.0)
    result = firewall.validate_order(order, stale_state)

    assert result["decision"] == "BLOCK"
    assert result["reason"] == "STALE_TELEMETRY_OR_INSOLVENT"


def test_risk_telemetry_report(firewall: RiskFirewall, healthy_state: PortfolioRiskState) -> None:
    """Verify industrial telemetry tracking of breaches."""
    # 1. ALLOW
    firewall.validate_order(OrderProposal("A", "B", 1, 1), healthy_state)
    # 2. BLOCK (VaR)
    firewall.validate_order(OrderProposal("B", "S", 1000000, 1), healthy_state)

    report = firewall.get_risk_report()
    assert report["allowed_orders"] == 1
    assert report["blocked_orders"] == 1
