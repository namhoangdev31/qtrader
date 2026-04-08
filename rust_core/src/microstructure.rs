use pyo3::prelude::*;
use std::collections::VecDeque;

#[pyclass]
pub struct MicrostructureEngine {
    pub core: MicrostructureCore,
}

#[pymethods]
impl MicrostructureEngine {
    #[new]
    pub fn new(window: usize) -> Self {
         MicrostructureEngine {
            core: MicrostructureCore::new(window),
        }
    }

    pub fn calculate_imbalance(&self, bid_size: f64, ask_size: f64) -> f64 {
        self.core.calculate_imbalance(bid_size, ask_size)
    }

    pub fn calculate_microprice(&self, bid_price: f64, ask_price: f64, bid_size: f64, ask_size: f64) -> f64 {
        self.core.calculate_microprice(bid_price, ask_price, bid_size, ask_size)
    }

    pub fn update_vpin(&mut self, tick_side: i32, volume: f64) -> f64 {
        self.core.update_vpin(tick_side, volume)
    }

    pub fn reset(&mut self) {
        self.core.reset();
    }
}

// --- Standalone Logic Core ---

pub struct MicrostructureCore {
    pub window: usize,
    buy_vol_buffer: VecDeque<f64>,
    sell_vol_buffer: VecDeque<f64>,
}

impl MicrostructureCore {
    pub fn new(window: usize) -> Self {
        MicrostructureCore {
            window,
            buy_vol_buffer: VecDeque::with_capacity(window),
            sell_vol_buffer: VecDeque::with_capacity(window),
        }
    }

    pub fn calculate_imbalance(&self, bid_size: f64, ask_size: f64) -> f64 {
        let total = bid_size + ask_size;
        if total > 0.0 { (bid_size - ask_size) / total } else { 0.0 }
    }

    pub fn calculate_microprice(&self, bid_price: f64, ask_price: f64, bid_size: f64, ask_size: f64) -> f64 {
        let total = bid_size + ask_size;
        if total > 0.0 {
            (bid_price * ask_size + ask_price * bid_size) / total
        } else {
            (bid_price + ask_price) / 2.0
        }
    }

    pub fn update_vpin(&mut self, tick_side: i32, volume: f64) -> f64 {
        let (buy_v, sell_v) = if tick_side > 0 { (volume, 0.0) } else { (0.0, volume) };
        if self.buy_vol_buffer.len() >= self.window {
            self.buy_vol_buffer.pop_front();
            self.sell_vol_buffer.pop_front();
        }
        self.buy_vol_buffer.push_back(buy_v);
        self.sell_vol_buffer.push_back(sell_v);
        let buy_sum: f64 = self.buy_vol_buffer.iter().sum();
        let sell_sum: f64 = self.sell_vol_buffer.iter().sum();
        let total_sum = buy_sum + sell_sum;
        if total_sum > 0.0 { (buy_sum - sell_sum).abs() / total_sum } else { 0.0 }
    }

    pub fn reset(&mut self) {
        self.buy_vol_buffer.clear();
        self.sell_vol_buffer.clear();
    }
}
