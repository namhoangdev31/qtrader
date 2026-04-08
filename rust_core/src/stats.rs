use pyo3::prelude::*;
use std::cmp::Ordering;

/// Advanced statistical functions for risk and performance estimation.
#[pyclass]
pub struct StatsEngine;

#[pymethods]
impl StatsEngine {
    #[new]
    pub fn new() -> Self {
        StatsEngine
    }

    /// Calculates Historical Expected Shortfall (CVaR) at confidence level alpha.
    /// Alpha is typically 0.05 (5%) or 0.01 (1%).
    #[pyo3(signature = (returns, alpha=0.05))]
    pub fn calculate_historical_es(&self, returns: Vec<f64>, alpha: f64) -> f64 {
        calculate_historical_es_logic(returns, alpha)
    }

    #[pyo3(signature = (returns, mar=0.0))]
    pub fn calculate_omega_ratio(&self, returns: Vec<f64>, mar: f64) -> f64 {
        calculate_omega_ratio_logic(returns, mar)
    }

    #[pyo3(signature = (returns, mar=0.0, periods=252.0))]
    pub fn calculate_sortino_ratio(&self, returns: Vec<f64>, mar: f64, periods: f64) -> f64 {
        calculate_sortino_ratio_logic(returns, mar, periods)
    }

    #[pyo3(signature = (annual_return, max_drawdown))]
    pub fn calculate_calmar_ratio(&self, annual_return: f64, max_drawdown: f64) -> f64 {
        calculate_calmar_ratio_logic(annual_return, max_drawdown)
    }

    pub fn calculate_mean(&self, data: Vec<f64>) -> f64 {
        if data.is_empty() { return 0.0; }
        data.iter().sum::<f64>() / data.len() as f64
    }

    pub fn calculate_std(&self, data: Vec<f64>) -> f64 {
        if data.len() < 2 { return 0.0; }
        let mean = self.calculate_mean(data.clone());
        let variance = data.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / data.len() as f64;
        variance.sqrt()
    }

    pub fn calculate_z_score(&self, value: f64, mean: f64, std: f64) -> f64 {
        if std < 1e-9 { return 0.0; }
        (value - mean) / std
    }
}

// --- Standalone Logic Functions (Testable without PyO3) ---

pub fn calculate_historical_es_logic(mut returns: Vec<f64>, alpha: f64) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }
    returns.sort_by(|a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal));
    let n_tail = (returns.len() as f64 * alpha).ceil() as usize;
    let n_tail = n_tail.max(1);
    let tail_sum: f64 = returns.iter().take(n_tail).sum();
    tail_sum / (n_tail as f64)
}

pub fn calculate_omega_ratio_logic(returns: Vec<f64>, mar: f64) -> f64 {
    let mut gains_sum = 0.0;
    let mut losses_sum = 0.0;
    for &r in &returns {
        if r > mar {
            gains_sum += r - mar;
        } else {
            losses_sum += mar - r;
        }
    }
    if losses_sum > 0.0 {
        gains_sum / losses_sum
    } else {
        f64::INFINITY
    }
}

pub fn calculate_sortino_ratio_logic(returns: Vec<f64>, mar: f64, periods: f64) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }
    let mean_return = returns.iter().sum::<f64>() / returns.len() as f64;
    let downside_returns: Vec<f64> = returns
        .iter()
        .filter(|&&r| r < mar)
        .map(|&r| (r - mar).powi(2))
        .collect();
    if downside_returns.is_empty() {
        return f64::INFINITY;
    }
    let downside_deviation = (downside_returns.iter().sum::<f64>() / returns.len() as f64).sqrt();
    if downside_deviation > 0.0 {
        (mean_return - mar) / downside_deviation * periods.sqrt()
    } else {
        0.0
    }
}

pub fn calculate_calmar_ratio_logic(annual_return: f64, max_drawdown: f64) -> f64 {
    if max_drawdown.abs() > 1e-9 {
        annual_return / max_drawdown.abs()
    } else {
        0.0
    }
}

