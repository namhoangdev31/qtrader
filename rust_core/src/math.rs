use pyo3::prelude::*;

#[pyclass]
pub struct MathEngine;

#[pymethods]
impl MathEngine {
    #[new]
    pub fn new() -> Self {
        MathEngine
    }

    #[pyo3(signature = (equity_curve))]
    pub fn calculate_max_drawdown(&self, equity_curve: Vec<f64>) -> (f64, f64) {
        if equity_curve.is_empty() {
            return (0.0, 0.0);
        }

        let mut peak = equity_curve[0];
        let mut max_dd = 0.0;

        for &val in &equity_curve {
            if val > peak {
                peak = val;
            }
            let dd = (peak - val) / peak;
            if dd > max_dd {
                max_dd = dd;
            }
        }

        (max_dd, peak)
    }

    /// Calculates rolling standard deviation for a series.
    #[pyo3(signature = (series, window))]
    pub fn calculate_rolling_volatility(&self, series: Vec<f64>, window: usize) -> Vec<f64> {
        if series.len() < window {
            return vec![0.0; series.len()];
        }

        let mut results = vec![0.0; series.len()];

        for i in (window - 1)..series.len() {
            let win = &series[(i + 1 - window)..=i];
            let mean = win.iter().sum::<f64>() / (window as f64);
            let variance = win.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / (window as f64);
            results[i] = variance.sqrt();
        }

        results
    }
}
