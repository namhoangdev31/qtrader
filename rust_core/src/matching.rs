use std::collections::HashMap;
use crate::oms::{Order, Side, OrderStatus, OrderType};

/// Simulates order matching against market data.
pub struct MatchingEngine {
    pub latency_ms: i64,      // Simulated network and matching latency
    pub fee_rate: f64,        // e.g. 0.0005 for 5 bps
    pub slippage_bps: f64,    // Fixed slippage assumption
}

impl MatchingEngine {
    pub fn new(latency_ms: i64, fee_rate: f64, slippage_bps: f64) -> Self {
        MatchingEngine {
            latency_ms,
            fee_rate,
            slippage_bps,
        }
    }

    /// Process a list of open orders against the current tick/bar.
    /// Returns a list of (Order ID, Fill Qty, Fill Price, Commission).
    pub fn match_orders(
        &self,
        orders: &mut HashMap<u64, Order>,
        current_price: f64,
        tick_timestamp: i64,
    ) -> Vec<(u64, f64, f64, f64)> {
        let mut fills = Vec::new();

        for (id, order) in orders.iter_mut() {
            if order.status == OrderStatus::Filled || order.status == OrderStatus::Canceled {
                continue;
            }

            // Latency check
            if tick_timestamp < order.timestamp_ms + self.latency_ms {
                continue; // Order hasn't reached exchange yet
            }

            let mut executed = false;
            let mut exec_price = 0.0;

            match order.order_type {
                OrderType::Market => {
                    // Taker slippage execution
                    let slippage_mult = match order.side {
                        Side::Buy => 1.0 + (self.slippage_bps / 10000.0),
                        Side::Sell => 1.0 - (self.slippage_bps / 10000.0),
                    };
                    exec_price = current_price * slippage_mult;
                    executed = true;
                }
                OrderType::Limit => {
                    // Simple limit order matching
                    if (order.side == Side::Buy && current_price <= order.price) ||
                       (order.side == Side::Sell && current_price >= order.price) {
                        // Limit matched at order price or better
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
                let fill_qty = order.qty - order.filled_qty; // fill entire remaining
                
                // Update order state
                order.filled_qty += fill_qty;
                order.alloc_price = exec_price; // Assuming full fill for this sim
                order.status = OrderStatus::Filled;

                let commission = exec_price * fill_qty * self.fee_rate;

                fills.push((*id, fill_qty, exec_price, commission));
            }
        }

        fills
    }
}
