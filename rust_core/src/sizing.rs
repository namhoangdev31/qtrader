use pyo3::prelude::*;

/// Logic for position sizing using fractional Kelly Criterion.
#[pyclass]
pub struct SizingEngine;

#[pymethods]
impl SizingEngine {
    #[new]
    pub fn new() -> Self {
        SizingEngine
    }

    /// Calculates the optimal Kelly fraction for a single-asset trade.
    /// win_prob: Probability of winning (0.0 to 1.0)
    /// avg_win: Average win percentage (e.g., 0.05 for 5%)
    /// avg_loss: Average loss percentage (e.g., 0.02 for 2%)
    /// fraction: Fractional Kelly scaling (e.g., 0.5 for half-Kelly)
    #[pyo3(signature = (win_prob, win_ratio, fraction=0.5))]
    pub fn calculate_kelly_fraction(&self, win_prob: f64, win_ratio: f64, fraction: f64) -> f64 {
        calculate_kelly_fraction_logic(win_prob, win_ratio, fraction)
    }

    /// Calculates Optimal Multiple for a discrete distribution of returns.
    /// This is more accurate for non-normal empirical distributions.
    #[pyo3(signature = (returns, fraction=0.5))]
    pub fn calculate_growth_optimal_fraction(&self, returns: Vec<f64>, fraction: f64) -> f64 {
        calculate_growth_optimal_fraction_logic(returns, fraction)
    }
}

// --- Standalone Logic Functions ---

pub fn calculate_kelly_fraction_logic(win_prob: f64, win_ratio: f64, fraction: f64) -> f64 {
    if win_ratio <= 0.0 {
        return 0.0;
    }
    let p = win_prob;
    let q = 1.0 - p;
    let b = win_ratio; 
    let f_star = (p * b - q) / b;
    (f_star * fraction).max(0.0).min(1.0)
}

pub fn calculate_growth_optimal_fraction_logic(returns: Vec<f64>, fraction: f64) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }
    let mut best_f = 0.0;
    let mut max_expected_log = 0.0;

    for f_int in 0..101 {
        let f = (f_int as f64) / 100.0;
        let mut sum_log = 0.0;
        let mut possible = true;

        for &r in &returns {
            let val = 1.0 + f * r;
            if val <= 1e-9 {
                possible = false;
                break;
            }
            sum_log += val.ln();
        }

        if possible {
            let avg_log = sum_log / (returns.len() as f64);
            if avg_log > max_expected_log {
                max_expected_log = avg_log;
                best_f = f;
            }
        }
    }
    best_f * fraction
}

