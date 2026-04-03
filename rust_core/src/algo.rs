use crate::oms::{Order, OrderType, Side};
use pyo3::prelude::*;

#[pyclass]
pub struct TwapAlgo {
    #[pyo3(get, set)]
    pub total_qty: f64,
    #[pyo3(get, set)]
    pub duration_ms: i64,
    #[pyo3(get, set)]
    pub slice_count: usize,
    start_ts: i64,
    slices_executed: usize,
    next_order_id: u64,
}

#[pymethods]
impl TwapAlgo {
    #[new]
    #[pyo3(signature = (total_qty, duration_ms, slice_count, start_ts, next_order_id))]
    pub fn new(
        total_qty: f64,
        duration_ms: i64,
        slice_count: usize,
        start_ts: i64,
        next_order_id: u64,
    ) -> Self {
        TwapAlgo {
            total_qty,
            duration_ms,
            slice_count,
            start_ts,
            slices_executed: 0,
            next_order_id,
        }
    }

    /// Generate TWAP slices based on current timestamp.
    /// Returns a list of Order objects and auto-increments internal order ID counter.
    pub fn generate_slices(&mut self, current_ts: i64, symbol: &str, side: &Side) -> Vec<Order> {
        let mut orders = Vec::new();

        if self.slices_executed >= self.slice_count {
            return orders;
        }

        let interval_ms = self.duration_ms / (self.slice_count as i64);
        if interval_ms <= 0 {
            return orders;
        }

        let expected_slices = ((current_ts - self.start_ts) / interval_ms) as usize;
        let target_slices = expected_slices.min(self.slice_count);
        let to_execute = target_slices.saturating_sub(self.slices_executed);

        if to_execute > 0 {
            let slice_qty = self.total_qty / (self.slice_count as f64);
            for i in 0..to_execute {
                self.next_order_id += 1;
                let o = Order::new(
                    self.next_order_id,
                    symbol.to_string(),
                    *side,
                    slice_qty,
                    0.0,
                    OrderType::Market,
                    current_ts + (i as i64),
                );
                orders.push(o);
            }
            self.slices_executed += to_execute;
        }

        orders
    }

    /// Reset the algo for reuse.
    pub fn reset(&mut self, start_ts: i64, next_order_id: u64) {
        self.slices_executed = 0;
        self.start_ts = start_ts;
        self.next_order_id = next_order_id;
    }

    #[getter]
    fn is_complete(&self) -> bool {
        self.slices_executed >= self.slice_count
    }

    #[getter]
    fn progress(&self) -> f64 {
        if self.slice_count == 0 {
            return 1.0;
        }
        self.slices_executed as f64 / self.slice_count as f64
    }

    fn __repr__(&self) -> String {
        format!(
            "TwapAlgo(total_qty={}, duration_ms={}, slices={}/{})",
            self.total_qty, self.duration_ms, self.slices_executed, self.slice_count
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_twap_generates_slices() {
        let mut twap = TwapAlgo::new(100.0, 60000, 6, 0, 0); // 100 qty over 60s, 6 slices
        let orders = twap.generate_slices(10000, "BTC", &Side::Buy); // 10s in
        assert_eq!(orders.len(), 1); // 1 slice expected at 10s
        assert_eq!(twap.slices_executed, 1);
    }

    #[test]
    fn test_twap_catches_up() {
        let mut twap = TwapAlgo::new(100.0, 60000, 6, 0, 0);
        // Jump to 50s — should catch up 5 slices
        let orders = twap.generate_slices(50000, "BTC", &Side::Buy);
        assert_eq!(orders.len(), 5);
        assert_eq!(twap.slices_executed, 5);
    }

    #[test]
    fn test_twap_completes() {
        let mut twap = TwapAlgo::new(100.0, 60000, 6, 0, 0);
        twap.generate_slices(60000, "BTC", &Side::Buy);
        assert!(twap.is_complete());
        assert_eq!(twap.progress(), 1.0);
    }
}
