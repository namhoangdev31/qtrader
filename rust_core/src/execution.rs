use crate::oms::{Account, Order, Side};
use crate::risk::{RiskCore, WarModeState, RiskEngine};
use crate::router::{RoutingMode, SmartOrderRouter};
use pyo3::prelude::*;
use std::collections::HashMap;

#[pyclass]
pub struct ExecutionEngine {
    pub risk_core: RiskCore,
    pub router: SmartOrderRouter,
    #[pyo3(get, set)]
    pub max_retries: usize,
    pub account: Account,
    pub market_data: HashMap<String, f64>,
}

#[pymethods]
impl ExecutionEngine {
    #[new]
    #[pyo3(signature = (risk_engine, initial_capital=1000000.0, routing_mode=RoutingMode::Smart, max_retries=3))]
    pub fn new(risk_engine: &RiskEngine, initial_capital: f64, routing_mode: RoutingMode, max_retries: usize) -> Self {
        ExecutionEngine {
            risk_core: risk_engine.core.clone(),
            router: SmartOrderRouter::new(routing_mode, None, None),
            max_retries,
            account: Account::new(initial_capital),
            market_data: HashMap::new(),
        }
    }

    /// Primary entry point for order execution.
    /// Performs validation, routing, and impact estimation.
    pub fn execute_order(
        &mut self,
        order: Order,
        peak_equity: f64,
        market_px: HashMap<String, (f64, f64)>, // exchange -> (bid, ask)
    ) -> PyResult<Vec<(Order, String)>> {
        // Update local market data for risk checks
        for (sym, (bid, ask)) in &market_px {
            self.market_data.insert(sym.clone(), (bid + ask) / 2.0);
        }

        let current_price = market_px.get(&order.symbol)
            .map(|(b, a)| if order.side == Side::Buy { *a } else { *b })
            .unwrap_or(0.0);

        // 1. Pre-trade Risk Validation
        if let Err(e) = self.risk_core.check_order(&order, &self.account, current_price, peak_equity) {
            return Err(pyo3::exceptions::PyValueError::new_err(format!("Risk Check Failed: {}", e)));
        }

        // 2. Routing Decision
        let liquidity_data = HashMap::new(); // Placeholder
        let routed_orders = self.router.route_order(&order, market_px, liquidity_data);

        Ok(routed_orders)
    }

    /// Process an asynchronous fill notification from the exchange.
    pub fn update_fill(&mut self, symbol: String, side: Side, qty: f64, price: f64) {
        if let Some(pos) = self.account.positions.get_mut(&symbol) {
            pos.add_fill(side, qty, price);
        } else {
            let mut pos = crate::oms::Position::new(symbol.clone());
            pos.add_fill(side, qty, price);
            self.account.positions.insert(symbol, pos);
        }
        
        let signed_qty = match side {
            Side::Buy => qty,
            Side::Sell => -qty,
        };
        self.account.cash -= signed_qty * price;
    }

    pub fn update_market_price(&mut self, symbol: String, price: f64) {
        self.market_data.insert(symbol, price);
    }

    pub fn get_account(&self) -> Account {
        self.account.clone()
    }

    pub fn set_routing_mode(&mut self, mode: RoutingMode) {
        self.router.routing_mode = mode;
    }

    pub fn get_war_mode_state(&self) -> WarModeState {
        self.risk_core.state
    }
}
