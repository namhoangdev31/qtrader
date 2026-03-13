use pyo3::prelude::*;
use std::collections::{BTreeMap, BinaryHeap};
use std::cmp::Ordering;

#[derive(PartialEq, Debug)]
struct Order {
    price: f64,
    quantity: f64,
    order_id: String,
}

impl Eq for Order {}

impl Ord for Order {
    fn cmp(&self, other: &Self) -> Ordering {
        self.price.partial_cmp(&other.price).unwrap_or(Ordering::Equal)
    }
}

impl PartialOrd for Order {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[pyclass]
struct OrderbookEngine {
    // Sorted maps for price levels. Key = Price, Value = Quantity
    // BTreeMap keeps keys sorted: Bids (descending), Asks (ascending)
    bids: BTreeMap<i64, f64>, // Using i64 key for exact price matching (price * 10^precision)
    asks: BTreeMap<i64, f64>,
    precision_factor: f64,
}

#[pymethods]
impl OrderbookEngine {
    #[new]
    fn new(precision: i32) -> Self {
        OrderbookEngine {
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            precision_factor: 10.0f64.powi(precision),
        }
    }

    fn apply_l2_update(&mut self, side: String, price: f64, quantity: f64) -> PyResult<()> {
        let price_key = (price * self.precision_factor).round() as i64;
        
        if side == "BUY" {
            if quantity == 0.0 {
                self.bids.remove(&price_key);
            } else {
                self.bids.insert(price_key, quantity);
            }
        } else {
            if quantity == 0.0 {
                self.asks.remove(&price_key);
            } else {
                self.asks.insert(price_key, quantity);
            }
        }
        Ok(())
    }

    #[getter]
    fn best_bid(&self) -> PyResult<Option<f64>> {
        Ok(self.bids.keys().rev().next().map(|&p| p as f64 / self.precision_factor))
    }

    #[getter]
    fn best_ask(&self) -> PyResult<Option<f64>> {
        Ok(self.asks.keys().next().map(|&p| p as f64 / self.precision_factor))
    }

    fn get_depth(&self, levels: usize) -> PyResult<(Vec<(f64, f64)>, Vec<(f64, f64)>)> {
        let bid_depth: Vec<(f64, f64)> = self.bids.iter().rev().take(levels)
            .map(|(&p, &q)| (p as f64 / self.precision_factor, q)).collect();
        let ask_depth: Vec<(f64, f64)> = self.asks.iter().take(levels)
            .map(|(&p, &q)| (p as f64 / self.precision_factor, q)).collect();
        Ok((bid_depth, ask_depth))
    }

    /// Computes microstructure features in Rust and returns only the feature vector.
    /// Note: returning `Vec<f64>` copies data into Python; this is not zero-copy.
    fn compute_microstructure_features(&self) -> PyResult<Vec<f64>> {
        let best_bid = self.bids.keys().rev().next().map(|&p| p as f64 / self.precision_factor).unwrap_or(0.0);
        let best_ask = self.asks.keys().next().map(|&p| p as f64 / self.precision_factor).unwrap_or(0.0);
        
        let bid_qty = self.bids.values().rev().next().unwrap_or(&0.0);
        let ask_qty = self.asks.values().next().unwrap_or(&0.0);
        
        // 1. Spread pct
        let spread = if best_ask > 0.0 { (best_ask - best_bid) / best_ask } else { 0.0 };
        
        // 2. Order Imbalance
        let imbalance = if (bid_qty + ask_qty) > 0.0 { (bid_qty - ask_qty) / (bid_qty + ask_qty) } else { 0.0 };
        
        // 3. Mid-price
        let mid = (best_bid + best_ask) / 2.0;
        
        Ok(vec![spread, imbalance, mid])
    }
}

#[pyclass]
struct MatchingEngine {
    // Future: Rust-native internal matching
}

#[pyfunction]
fn rust_version() -> PyResult<String> {
    Ok("0.1.0-native-core".to_string())
}

#[pymodule]
fn qtrader_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rust_version, m)?)?;
    m.add_class::<OrderbookEngine>()?;
    m.add_class::<MatchingEngine>()?;
    Ok(())
}
