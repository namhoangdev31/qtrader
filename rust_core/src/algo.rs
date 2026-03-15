use crate::oms::{Order, OrderType, Side};

pub struct TwapAlgo {
    pub total_qty: f64,
    pub duration_ms: i64,
    pub slice_count: usize,
    start_ts: i64,
    slices_executed: usize,
}

impl TwapAlgo {
    pub fn new(total_qty: f64, duration_ms: i64, slice_count: usize, start_ts: i64) -> Self {
        TwapAlgo {
            total_qty,
            duration_ms,
            slice_count,
            start_ts,
            slices_executed: 0,
        }
    }

    pub fn generate_slices(
        &mut self,
        current_ts: i64,
        symbol: &str,
        side: Side,
        base_id: &mut u64,
    ) -> Vec<Order> {
        let mut orders = Vec::new();

        if self.slices_executed >= self.slice_count {
            return orders; // Done
        }

        let interval_ms = self.duration_ms / (self.slice_count as i64);
        let expected_slices = ((current_ts - self.start_ts) / interval_ms) as usize;
        
        // Catch up on missed slices up to max slice_count
        let target_slices = expected_slices.min(self.slice_count);
        let to_execute = target_slices.saturating_sub(self.slices_executed);

        if to_execute > 0 {
            let slice_qty = self.total_qty / (self.slice_count as f64);
            for i in 0..to_execute {
                *base_id += 1;
                let o = Order::new(
                    *base_id,
                    symbol.to_string(),
                    side,
                    slice_qty,
                    0.0,
                    OrderType::Market,
                    current_ts + (i as i64), // slightly stagger timestamp
                );
                orders.push(o);
            }
            self.slices_executed += to_execute;
        }

        orders
    }
}
