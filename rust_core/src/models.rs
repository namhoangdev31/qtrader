use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[pyclass]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlippageModel {
    #[pyo3(get, set)]
    pub temporary_impact: f64,
    #[pyo3(get, set)]
    pub permanent_impact: f64,
    #[pyo3(get, set)]
    pub volatility_factor: f64,
}

impl Default for SlippageModel {
    fn default() -> Self {
        SlippageModel {
            temporary_impact: 0.1,
            permanent_impact: 0.05,
            volatility_factor: 2.5,
        }
    }
}

#[pymethods]
impl SlippageModel {
    #[new]
    #[pyo3(signature = (temporary_impact=0.1, permanent_impact=0.05, volatility_factor=2.5))]
    pub fn new(temporary_impact: f64, permanent_impact: f64, volatility_factor: f64) -> Self {
        SlippageModel {
            temporary_impact,
            permanent_impact,
            volatility_factor,
        }
    }

    /// Compute expected slippage for an order.
    /// Returns expected slippage in price units (positive for adverse movement).
    pub fn compute_slippage(
        &self,
        side_is_buy: bool,
        quantity: f64,
        mid_price: f64,
        total_volume: f64,
        volatility: f64,
    ) -> f64 {
        if mid_price <= 0.0 || total_volume <= 0.0 {
            return mid_price * 0.01; // Fallback to 1% slippage
        }

        let participation_rate = (quantity / total_volume).min(1.0);
        let temporary = self.temporary_impact * participation_rate * mid_price;
        let permanent = self.permanent_impact * participation_rate.sqrt() * mid_price;
        let vol_component =
            self.volatility_factor * volatility * mid_price * participation_rate.sqrt();

        let mut slippage = temporary + permanent + vol_component;
        if !side_is_buy {
            slippage = -slippage;
        }
        slippage
    }
}

/// Realistic network delay simulator.
#[pyclass]
pub struct LatencyModel {
    #[pyo3(get, set)]
    pub base_latency_ms: i64,
    #[pyo3(get, set)]
    pub jitter_ms: i64,
}

#[pymethods]
impl LatencyModel {
    #[new]
    pub fn new(base_latency_ms: i64, jitter_ms: i64) -> Self {
        LatencyModel {
            base_latency_ms,
            jitter_ms,
        }
    }

    pub fn sample_latency(&self) -> i64 {
        self.base_latency_ms
    }
}
