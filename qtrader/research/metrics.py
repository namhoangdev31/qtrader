from __future__ import annotations

import polars as pl


def sharpe_ratio(returns, risk_free=0.0, periods_per_year=252):
    """
    Calculate the Sharpe ratio of a return series.

    Args:
        returns: A pl.Series of period returns (e.g., daily returns).
        risk_free: The risk-free rate per period (default 0.0).
        periods_per_year: Number of periods in a year for annualization (default 252 for trading days).

    Returns:
        The annualized Sharpe ratio as a float.
    """
    if returns.is_empty():
        return 0.0
    # Calculate excess returns
    excess_returns = returns - risk_free
    # Compute mean and standard deviation
    mean_excess = excess_returns.mean()
    std_excess = excess_returns.std()

    # Handle case where volatility is zero
    if std_excess == 0.0:
        return 0.0

    # Calculate Sharpe ratio and annualize
    sharpe = (mean_excess / std_excess) * (periods_per_year ** 0.5)
    return float(sharpe)


def sortino_ratio(returns, risk_free=0.0, periods_per_year=252):
    """
    Calculate the Sortino ratio of a return series.

    Args:
        returns: A pl.Series of period returns (e.g., daily returns).
        risk_free: The risk-free rate per period (default 0.0).
        periods_per_year: Number of periods in a year for annualization (default 252 for trading days).

    Returns:
        The annualized Sortino ratio as a float.
    """
    if returns.is_empty():
        return 0.0
    # Calculate excess returns
    excess_returns = returns - risk_free
    mean_excess = excess_returns.mean()

    # If mean excess is zero, Sortino ratio is zero
    if mean_excess == 0.0:
        return 0.0

    # Calculate downside deviation: set positive excess returns to 0, then compute std
    downside_returns = excess_returns * (excess_returns < 0)
    downside_deviation = downside_returns.std()

    # Handle case where downside deviation is zero
    if downside_deviation == 0.0:
        return 0.0

    # Calculate Sortino ratio and annualize
    sortino = (mean_excess / downside_deviation) * (periods_per_year ** 0.5)
    return float(sortino)


def max_drawdown(returns):
    """
    Calculate the maximum drawdown of a return series.

    Args:
        returns: A pl.Series of period returns (e.g., daily returns).

    Returns:
        The maximum drawdown as a positive float (e.g., 0.15 for 15% drawdown).
    """
    if returns.is_empty():
        return 0.0
    # Calculate cumulative returns
    cum_returns = (1.0 + returns).cum_prod()
    # Calculate running maximum
    running_max = cum_returns.cum_max()
    # Calculate drawdown
    drawdown = (cum_returns - running_max) / running_max
    # The maximum drawdown is the minimum (most negative) drawdown
    max_dd = drawdown.min()
    # Return as positive number
    return abs(float(max_dd))


def calmar_ratio(returns, periods_per_year=252):
    """
    Calculate the Calmar ratio of a return series.

    Args:
        returns: A pl.Series of period returns (e.g., daily returns).
        periods_per_year: Number of periods in a year for annualization (default 252 for trading days).

    Returns:
        The Calmar ratio as a float.
    """
    if returns.is_empty():
        return 0.0
    # Calculate total return using cumulative product
    cum_returns = (1.0 + returns).cum_prod()
    total_return = float(cum_returns[-1] - 1.0)
    n_periods = len(returns)
    # Avoid division by zero in annualization
    if n_periods == 0:
        return 0.0
    # Calculate annualized return
    annualized_return = (1.0 + total_return) ** (periods_per_year / n_periods) - 1.0

    # Calculate maximum drawdown
    dd = max_drawdown(returns)

    # Handle case where drawdown is zero
    if dd == 0.0:
        return 0.0

    # Calculate Calmar ratio
    calmar = annualized_return / dd
    return float(calmar)