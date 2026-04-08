use crate::oms::{Order, OrderType, Side};
use pyo3::prelude::*;
use std::collections::HashMap;

#[pyclass]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RoutingMode {
    Manual,
    BestPrice,
    Smart,
}

#[pyclass]
pub struct SmartOrderRouter {
    #[pyo3(get, set)]
    pub routing_mode: RoutingMode,
    #[pyo3(get, set)]
    pub max_order_size: Option<f64>,
    #[pyo3(get, set)]
    pub split_size: Option<f64>,
    pub fees: HashMap<String, (f64, f64)>,
    pub latency: HashMap<String, i64>,
}

#[pymethods]
impl SmartOrderRouter {
    #[new]
    #[pyo3(signature = (routing_mode=RoutingMode::Smart, max_order_size=None, split_size=None))]
    pub fn new(
        routing_mode: RoutingMode,
        max_order_size: Option<f64>,
        split_size: Option<f64>,
    ) -> Self {
        SmartOrderRouter {
            routing_mode,
            max_order_size,
            split_size,
            fees: HashMap::new(),
            latency: HashMap::new(),
        }
    }

    pub fn set_fee(&mut self, exchange: String, maker: f64, taker: f64) {
        self.fees.insert(exchange, (maker, taker));
    }

    pub fn set_latency(&mut self, exchange: String, latency_ms: i64) {
        self.latency.insert(exchange, latency_ms);
    }

    /// Route a parent order to best exchange(es).
    pub fn route_order(
        &self,
        order: &Order,
        market_data: HashMap<String, (f64, f64)>, // exchange_name -> (best_bid, best_ask)
        liquidity_data: HashMap<String, (f64, f64)>, // exchange_name -> (bid_qty, ask_qty)
    ) -> Vec<(Order, String)> {
        if let Some(max_size) = self.max_order_size {
            if order.qty > max_size {
                return self.split_and_route(order, &market_data, &liquidity_data);
            }
        }

        let exchange = self.select_exchange(order, &market_data, &liquidity_data);
        vec![(order.clone(), exchange)]
    }
}

impl SmartOrderRouter {
    fn select_exchange(
        &self,
        order: &Order,
        market_data: &HashMap<String, (f64, f64)>,
        liquidity_data: &HashMap<String, (f64, f64)>,
    ) -> String {
        match self.routing_mode {
            RoutingMode::Manual => market_data
                .keys()
                .next()
                .cloned()
                .unwrap_or_else(|| "UNKNOWN".to_string()),
            RoutingMode::BestPrice => self.select_best_price(order, market_data),
            RoutingMode::Smart => self.select_smart(order, market_data, liquidity_data),
        }
    }

    fn select_best_price(
        &self,
        order: &Order,
        market_data: &HashMap<String, (f64, f64)>,
    ) -> String {
        let mut best_exchange = None;
        let mut best_px = if order.side == Side::Buy {
            f64::MAX
        } else {
            f64::MIN
        };

        for (exchange, (bid, ask)) in market_data {
            match order.side {
                Side::Buy => {
                    if *ask < best_px {
                        best_px = *ask;
                        best_exchange = Some(exchange.clone());
                    }
                }
                Side::Sell => {
                    if *bid > best_px {
                        best_px = *bid;
                        best_exchange = Some(exchange.clone());
                    }
                }
            }
        }
        best_exchange.unwrap_or_else(|| "UNKNOWN".to_string())
    }

    fn select_smart(
        &self,
        order: &Order,
        market_data: &HashMap<String, (f64, f64)>,
        liquidity_data: &HashMap<String, (f64, f64)>,
    ) -> String {
        let mut best_exchange = None;
        let mut max_score = f64::MIN;

        for (exchange, (bid, ask)) in market_data {
            let mut score = 0.0;
            let px = if order.side == Side::Buy { *ask } else { *bid };
            let px_score = if order.side == Side::Buy {
                1.0 / px
            } else {
                px
            };
            score += px_score * 1000.0;

            if let Some((bid_liq, ask_px_liq)) = liquidity_data.get(exchange) {
                let liq = if order.side == Side::Buy {
                    *ask_px_liq
                } else {
                    *bid_liq
                };
                score += liq.min(order.qty) / order.qty * 100.0;
            }

            if let Some((maker, taker)) = self.fees.get(exchange) {
                let fee = if order.order_type == OrderType::Market {
                    *taker
                } else {
                    *maker
                };
                score -= fee * 500.0;
            }

            if let Some(lat) = self.latency.get(exchange) {
                score -= (*lat as f64) / 10.0;
            }

            if score > max_score {
                max_score = score;
                best_exchange = Some(exchange.clone());
            }
        }
        best_exchange.unwrap_or_else(|| "UNKNOWN".to_string())
    }

    fn split_and_route(
        &self,
        order: &Order,
        market_data: &HashMap<String, (f64, f64)>,
        liquidity_data: &HashMap<String, (f64, f64)>,
    ) -> Vec<(Order, String)> {
        let mut results = Vec::new();
        let split_qty = self.split_size.unwrap_or(order.qty / 2.0);
        let mut remaining = order.qty;
        let mut i = 0;

        while remaining > 0.0 {
            let qty = split_qty.min(remaining);
            let mut sub_order = order.clone();
            sub_order.qty = qty;
            sub_order.id = format!("{}-{}", order.id, i);

            let exchange = self.select_exchange(&sub_order, market_data, liquidity_data);
            results.push((sub_order, exchange));
            remaining -= qty;
            i += 1;
        }
        results
    }
}
