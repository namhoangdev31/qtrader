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

#[pyclass]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrderStatus {
    New,       // NEW
    Ack,       // ACK
    Partial,   // PARTIAL
    Filled,    // FILLED
    Closed,    // CLOSED
    Rejected,  // REJECTED
}

/// A standard execution order.
#[pyclass]
#[derive(Debug, Clone)]
pub struct Order {
    #[pyo3(get)]
    pub id: String,
    #[pyo3(get)]
    pub symbol: String,
    #[pyo3(get)]
    pub side: Side,
    #[pyo3(get)]
    pub qty: f64,
    #[pyo3(get)]
    pub price: f64, // 0.0 for Market
    #[pyo3(get)]
    pub order_type: OrderType,
    #[pyo3(get, set)]
    pub status: OrderStatus,
    #[pyo3(get, set)]
    pub filled_qty: f64,
    #[pyo3(get, set)]
    pub alloc_price: f64, // Average fill price
    #[pyo3(get)]
    pub timestamp_ms: i64,
}

#[pymethods]
impl Order {
    #[new]
    #[pyo3(signature = (id, symbol, side, qty, price, order_type, timestamp_ms))]
    pub fn new(
        id: String,
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
            status: OrderStatus::New,
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
    pub qty: f64, // Positive: Long, Negative: Short
    #[pyo3(get, set)]
    pub avg_entry_price: f64,
}

#[pymethods]
impl Position {
    #[new]
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

        if new_qty.abs() > 1e-9 {
            if self.qty.signum() == signed_fill.signum() || self.qty == 0.0 {
                let prior_value = self.qty.abs() * self.avg_entry_price;
                let add_value = fill_qty * fill_price;
                self.avg_entry_price = (prior_value + add_value) / new_qty.abs();
            } else {
                if new_qty.signum() != self.qty.signum() {
                    self.avg_entry_price = fill_price;
                }
            }
        } else {
            self.avg_entry_price = 0.0;
        }

        self.qty = new_qty;
    }

    fn __repr__(&self) -> String {
        format!(
            "Position(symbol={}, qty={}, avg_price={})",
            self.symbol, self.qty, self.avg_entry_price
        )
    }
}

/// State of the trading account (Balance + open positions).
#[pyclass]
#[derive(Debug, Clone)]
pub struct Account {
    #[pyo3(get)]
    pub initial_capital: f64,
    #[pyo3(get, set)]
    pub cash: f64,
    #[pyo3(get)]
    pub positions: HashMap<String, Position>,
    #[pyo3(get)]
    pub total_commissions: f64,
}

#[pymethods]
impl Account {
    #[new]
    pub fn new(initial_capital: f64) -> Self {
        Account {
            initial_capital,
            cash: initial_capital,
            positions: HashMap::new(),
            total_commissions: 0.0,
        }
    }

    pub fn get_position(&self, symbol: &str) -> Option<Position> {
        self.positions.get(symbol).cloned()
    }

    pub fn set_position(&mut self, symbol: String, position: Position) {
        self.positions.insert(symbol, position);
    }

    pub fn add_position_direct(&mut self, symbol: String, qty: f64, avg_price: f64) {
        let mut pos = Position::new(symbol.clone());
        pos.qty = qty;
        pos.avg_entry_price = avg_price;
        self.positions.insert(symbol, pos);
    }

    pub fn equity(&self, current_prices: HashMap<String, f64>) -> f64 {
        let mut eq = self.cash;
        for (sym, pos) in &self.positions {
            if let Some(&price) = current_prices.get(sym) {
                let unpnl = pos.qty * (price - pos.avg_entry_price);
                eq += pos.qty * pos.avg_entry_price + unpnl;
            }
        }
        eq
    }

    fn __repr__(&self) -> String {
        format!(
            "Account(cash={}, positions={}, commissions={})",
            self.cash,
            self.positions.len(),
            self.total_commissions
        )
    }
}

impl Account {
    pub fn equity_internal(&self, current_prices: &HashMap<String, f64>) -> f64 {
        let mut eq = self.cash;
        for (sym, pos) in &self.positions {
            if let Some(&price) = current_prices.get(sym) {
                let unpnl = pos.qty * (price - pos.avg_entry_price);
                eq += pos.qty * pos.avg_entry_price + unpnl;
            }
        }
        eq
    }
}
