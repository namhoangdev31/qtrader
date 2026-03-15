use pyo3::prelude::*;
use std::collections::HashMap;

/// Order side (Buy or Sell).
#[pyclass]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    Buy,
    Sell,
}

/// Type of the order (Market, Limit, etc.).
#[pyclass]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrderType {
    Market,
    Limit,
    Stop,
}

/// Status of an order in the OMS.
#[pyclass]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrderStatus {
    Pending,
    Open,
    PartialFill,
    Filled,
    Canceled,
    Rejected,
}

/// A standard execution order.
#[pyclass]
#[derive(Debug, Clone)]
pub struct Order {
    #[pyo3(get)]
    pub id: u64,
    #[pyo3(get)]
    pub symbol: String,
    #[pyo3(get)]
    pub side: Side,
    #[pyo3(get)]
    pub qty: f64,
    #[pyo3(get)]
    pub price: f64,          // 0.0 for Market
    #[pyo3(get)]
    pub order_type: OrderType,
    #[pyo3(get, set)]
    pub status: OrderStatus,
    #[pyo3(get, set)]
    pub filled_qty: f64,
    #[pyo3(get, set)]
    pub alloc_price: f64,    // Average fill price
    #[pyo3(get)]
    pub timestamp_ms: i64,
}

#[pymethods]
impl Order {
    #[new]
    #[pyo3(signature = (id, symbol, side, qty, price, order_type, timestamp_ms))]
    pub fn new(
        id: u64,
        symbol: String,
        side: Side,
        qty: f64,
        price: f64,
        order_type: OrderType,
        timestamp_ms: i64,
    ) -> Self {
        Order {
            id,
            symbol,
            side,
            qty,
            price,
            order_type,
            status: OrderStatus::Pending,
            filled_qty: 0.0,
            alloc_price: 0.0,
            timestamp_ms,
        }
    }
}

/// Represents the current holding for a specific symbol.
#[pyclass]
#[derive(Debug, Clone)]
pub struct Position {
    #[pyo3(get)]
    pub symbol: String,
    #[pyo3(get, set)]
    pub qty: f64,            // Positive: Long, Negative: Short
    #[pyo3(get, set)]
    pub avg_entry_price: f64,
}

impl Position {
    pub fn new(symbol: String) -> Self {
        Position {
            symbol,
            qty: 0.0,
            avg_entry_price: 0.0,
        }
    }

    pub fn add_fill(&mut self, side: Side, fill_qty: f64, fill_price: f64) {
        let signed_fill = match side {
            Side::Buy => fill_qty,
            Side::Sell => -fill_qty,
        };

        let new_qty = self.qty + signed_fill;

        // Simplified average price calculation (VWAP of position)
        if new_qty.abs() > 1e-9 {
            if self.qty.signum() == signed_fill.signum() || self.qty == 0.0 {
                // Adding to same side position
                let prior_value = self.qty.abs() * self.avg_entry_price;
                let add_value = fill_qty * fill_price;
                self.avg_entry_price = (prior_value + add_value) / new_qty.abs();
            } else {
                // Reversing or reducing position
                if new_qty.signum() != self.qty.signum() {
                    // Flipped position
                    self.avg_entry_price = fill_price;
                }
            }
        } else {
            // Flat
            self.avg_entry_price = 0.0;
        }

        self.qty = new_qty;
    }
}

/// State of the trading account (Balance + open positions).
#[derive(Debug)]
pub struct Account {
    pub initial_capital: f64,
    pub cash: f64,
    pub positions: HashMap<String, Position>,
    pub total_commissions: f64,
}

impl Account {
    pub fn new(initial_capital: f64) -> Self {
        Account {
            initial_capital,
            cash: initial_capital,
            positions: HashMap::new(),
            total_commissions: 0.0,
        }
    }

    pub fn equity(&self, current_prices: &HashMap<String, f64>) -> f64 {
        let mut eq = self.cash;
        for (sym, pos) in &self.positions {
            if let Some(&price) = current_prices.get(sym) {
                // UnPnL
                let unpnl = pos.qty * (price - pos.avg_entry_price);
                // Value of pos + pnL (simplified for delta)
                eq += pos.qty * pos.avg_entry_price + unpnl;
            }
        }
        eq
    }
}
