use crate::oms::{Order, OrderStatus, OrderType, Side};
use pyo3::prelude::*;
use std::collections::HashMap;

/// Simulates order matching against market data.
#[pyclass]
pub struct MatchingEngine {
    #[pyo3(get, set)]
    pub latency_ms: i64,
    #[pyo3(get, set)]
    pub fee_rate: f64,
    #[pyo3(get, set)]
    pub slippage_bps: f64,
}

#[pymethods]
impl MatchingEngine {
    #[new]
    #[pyo3(signature = (latency_ms, fee_rate, slippage_bps))]
    pub fn new(latency_ms: i64, fee_rate: f64, slippage_bps: f64) -> Self {
        MatchingEngine {
            latency_ms,
            fee_rate,
            slippage_bps,
        }
    }

    /// Process a single order against the current market price.
    /// Returns (fill_qty, fill_price, commission) or None if not filled.
    pub fn match_single(
        &self,
        order: &mut Order,
        current_price: f64,
        tick_timestamp: i64,
    ) -> Option<(f64, f64, f64)> {
        if order.status == OrderStatus::Filled || order.status == OrderStatus::Closed {
            return None;
        }
        if tick_timestamp < order.timestamp_ms + self.latency_ms {
            return None;
        }

        let mut executed = false;
        let mut exec_price = 0.0;

        match order.order_type {
            OrderType::Market => {
                let slippage_mult = match order.side {
                    Side::Buy => 1.0 + (self.slippage_bps / 10000.0),
                    Side::Sell => 1.0 - (self.slippage_bps / 10000.0),
                };
                exec_price = current_price * slippage_mult;
                executed = true;
            }
            OrderType::Limit => {
                if (order.side == Side::Buy && current_price <= order.price)
                    || (order.side == Side::Sell && current_price >= order.price)
                {
                    exec_price = if order.side == Side::Buy {
                        current_price.min(order.price)
                    } else {
                        current_price.max(order.price)
                    };
                    executed = true;
                }
            }
            _ => {}
        }

        if executed {
            let fill_qty = order.qty - order.filled_qty;
            order.filled_qty += fill_qty;
            order.alloc_price = exec_price;
            order.status = OrderStatus::Filled;
            let commission = exec_price * fill_qty * self.fee_rate;
            Some((fill_qty, exec_price, commission))
        } else {
            None
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "MatchingEngine(latency_ms={}, fee_rate={}, slippage_bps={})",
            self.latency_ms, self.fee_rate, self.slippage_bps
        )
    }
}

impl MatchingEngine {
    /// Internal: Process a HashMap of orders (used by simulator).
    pub fn match_orders(
        &self,
        orders: &mut HashMap<String, Order>,
        current_price: f64,
        tick_timestamp: i64,
    ) -> Vec<(String, f64, f64, f64)> {
        let mut fills = Vec::new();
        for (id, order) in orders.iter_mut() {
            if order.status == OrderStatus::Filled || order.status == OrderStatus::Closed {
                continue;
            }
            if tick_timestamp < order.timestamp_ms + self.latency_ms {
                continue;
            }

            let mut executed = false;
            let mut exec_price = 0.0;

            match order.order_type {
                OrderType::Market => {
                    let slippage_mult = match order.side {
                        Side::Buy => 1.0 + (self.slippage_bps / 10000.0),
                        Side::Sell => 1.0 - (self.slippage_bps / 10000.0),
                    };
                    exec_price = current_price * slippage_mult;
                    executed = true;
                }
                OrderType::Limit => {
                    if (order.side == Side::Buy && current_price <= order.price)
                        || (order.side == Side::Sell && current_price >= order.price)
                    {
                        exec_price = if order.side == Side::Buy {
                            current_price.min(order.price)
                        } else {
                            current_price.max(order.price)
                        };
                        executed = true;
                    }
                }
                _ => {}
            }

            if executed {
                let fill_qty = order.qty - order.filled_qty;
                order.filled_qty += fill_qty;
                order.alloc_price = exec_price;
                order.status = OrderStatus::Filled;
                let commission = exec_price * fill_qty * self.fee_rate;
                fills.push((id.clone(), fill_qty, exec_price, commission));
            }
        }
        fills
    }
}
