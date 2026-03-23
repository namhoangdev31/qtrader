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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_matching_engine_market_order() {
        let matching = MatchingEngine::new(0, 0.0005, 10.0);
        let mut orders = HashMap::new();
        let order = Order::new(1, "BTC".to_string(), Side::Buy, 1.0, 0.0, OrderType::Market, 1000);
        orders.insert(1, order);

        let fills = matching.match_orders(&mut orders, 50000.0, 2000);
        assert_eq!(fills.len(), 1);
        let (_, qty, price, comm) = fills[0];
        assert_eq!(qty, 1.0);
        assert_eq!(price, 50000.0 * 1.001); // 10 bps slippage
        assert_eq!(comm, price * qty * 0.0005);
    }

    #[test]
    fn test_matching_engine_limit_order() {
        let matching = MatchingEngine::new(0, 0.0, 0.0);
        let mut orders = HashMap::new();
        
        let buy_order = Order::new(1, "BTC".to_string(), Side::Buy, 1.0, 49000.0, OrderType::Limit, 1000);
        orders.insert(1, buy_order);

        // Current @ 50000 -> No match
        let fills_1 = matching.match_orders(&mut orders, 50000.0, 2000);
        assert_eq!(fills_1.len(), 0);

        // Current @ 48000 -> Match
        let fills_2 = matching.match_orders(&mut orders, 48000.0, 3000);
        assert_eq!(fills_2.len(), 1);
        assert_eq!(fills_2[0].2, 48000.0); // Filled at best available
    }

    #[test]
    fn test_matching_engine_latency() {
        let matching = MatchingEngine::new(100, 0.0, 0.0);
        let mut orders = HashMap::new();
        let order = Order::new(1, "BTC".to_string(), Side::Buy, 1.0, 0.0, OrderType::Market, 1000);
        orders.insert(1, order);

        // tick @ 1050 < 1000 + 100 -> No match
        let fills_1 = matching.match_orders(&mut orders, 50000.0, 1050);
        assert_eq!(fills_1.len(), 0);

        // tick @ 1100 -> Match
        let fills_2 = matching.match_orders(&mut orders, 50000.0, 1100);
        assert_eq!(fills_2.len(), 1);
    }

    #[test]
    fn test_matching_engine_limit_sell_order() {
        let matching = MatchingEngine::new(0, 0.0, 0.0);
        let mut orders = HashMap::new();
        
        let sell_order = Order::new(2, "ETH".to_string(), Side::Sell, 5.0, 3000.0, OrderType::Limit, 1000);
        orders.insert(2, sell_order);

        // Current @ 2900 -> No match (Sell limit needs price >= limit)
        let fills_1 = matching.match_orders(&mut orders, 2900.0, 2000);
        assert_eq!(fills_1.len(), 0);

        // Current @ 3100 -> Match
        let fills_2 = matching.match_orders(&mut orders, 3100.0, 3000);
        assert_eq!(fills_2.len(), 1);
        assert_eq!(fills_2[0].2, 3100.0); // Filled at best available
    }

    #[test]
    fn test_matching_engine_slippage_calculation() {
        // 0.01 fractional slippage = 1%
        let matching = MatchingEngine::new(0, 0.0, 0.01); 
        let mut orders = HashMap::new();
        
        // Buy Market order
        let buy_order = Order::new(1, "BTC".to_string(), Side::Buy, 1.0, 0.0, OrderType::Market, 1000);
        orders.insert(1, buy_order);
        
        // Sell Market order
        let sell_order = Order::new(2, "BTC".to_string(), Side::Sell, 1.0, 0.0, OrderType::Market, 1000);
        orders.insert(2, sell_order);

        let fills = matching.match_orders(&mut orders, 50000.0, 2000);
        assert_eq!(fills.len(), 2);
        
        // Fills are returned in order of hash map iteration (which isn't strictly defined)
        // Let's find each by Side (we know sell prices will be lower, buy prices higher)
        // Wait, fills is returning (order_id, qty, price, comm)
        for fill in fills {
            if fill.0 == 1 {
                assert_eq!(fill.2, 50500.0); // Buy: 50000 * 1.01
            } else if fill.0 == 2 {
                assert_eq!(fill.2, 49500.0); // Sell: 50000 * 0.99
            }
        }
    }
}
