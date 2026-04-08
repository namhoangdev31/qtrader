use crate::oms::{Account, Order, OrderStatus, Side};
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

#[pyclass]
#[derive(Debug, Clone)]
pub struct OrderFSM {
    pub pending_timeout_s: f64,
}

#[pymethods]
impl OrderFSM {
    #[new]
    pub fn new(pending_timeout_s: f64) -> Self {
        OrderFSM { pending_timeout_s }
    }

    pub fn transition(&self, current_state: OrderStatus, event: String) -> PyResult<OrderStatus> {
        match current_state {
            OrderStatus::New => {
                if event == "ACK" { return Ok(OrderStatus::Ack); }
                if event == "REJECT" { return Ok(OrderStatus::Rejected); }
            }
            OrderStatus::Ack => {
                if event == "FILL_PARTIAL" { return Ok(OrderStatus::Partial); }
                if event == "FILL_COMPLETE" { return Ok(OrderStatus::Filled); }
                if event == "CANCEL" { return Ok(OrderStatus::Closed); }
                if event == "REJECT" { return Ok(OrderStatus::Rejected); }
            }
            OrderStatus::Partial => {
                if event == "FILL_PARTIAL" { return Ok(OrderStatus::Partial); }
                if event == "FILL_COMPLETE" { return Ok(OrderStatus::Filled); }
                if event == "CANCEL" { return Ok(OrderStatus::Closed); }
            }
            OrderStatus::Filled | OrderStatus::Closed | OrderStatus::Rejected => {
                return Ok(current_state);
            }
        }
        Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Invalid transition from {:?} on event {}",
            current_state, event
        )))
    }
}

#[pyclass]
pub struct UnifiedOMS {
    pub active_orders: Arc<RwLock<HashMap<String, Order>>>,
    pub account: Arc<RwLock<Account>>,
    pub fsm: OrderFSM,
}

#[pymethods]
impl UnifiedOMS {
    #[new]
    pub fn new(initial_capital: f64, pending_timeout_s: f64) -> Self {
        UnifiedOMS {
            active_orders: Arc::new(RwLock::new(HashMap::new())),
            account: Arc::new(RwLock::new(Account::new(initial_capital))),
            fsm: OrderFSM::new(pending_timeout_s),
        }
    }

    pub fn create_order(&self, order: Order) -> PyResult<()> {
        let mut orders = self.active_orders.write().unwrap();
        orders.insert(order.id.clone(), order);
        Ok(())
    }

    pub fn on_ack(&self, order_id: String) -> PyResult<Order> {
        self._transition(order_id, "ACK".to_string())
    }

    pub fn on_reject(&self, order_id: String) -> PyResult<Order> {
        self._transition(order_id, "REJECT".to_string())
    }

    pub fn on_cancel(&self, order_id: String) -> PyResult<Order> {
        self._transition(order_id, "CANCEL".to_string())
    }

    pub fn on_fill(&self, order_id: String, qty: f64, price: f64) -> PyResult<(Order, crate::oms::Position, f64)> {
        let mut orders = self.active_orders.write().unwrap();
        if let Some(order) = orders.get_mut(&order_id) {
            let is_complete = (order.filled_qty + qty) >= order.qty;
            let event = if is_complete { "FILL_COMPLETE" } else { "FILL_PARTIAL" };
            
            // Transition state
            order.status = self.fsm.transition(order.status, event.to_string())?;
            order.filled_qty += qty;
            
            // Update Position and Cash
            let mut account = self.account.write().unwrap();
            let mut pos = account.get_position(&order.symbol).unwrap_or_else(|| crate::oms::Position::new(order.symbol.clone()));
            pos.add_fill(order.side, qty, price);
            account.set_position(order.symbol.clone(), pos.clone());
            
            let signed_qty = match order.side {
                Side::Buy => qty,
                Side::Sell => -qty,
            };
            account.cash -= signed_qty * price;

            return Ok((order.clone(), pos, account.cash));
        }
        Err(pyo3::exceptions::PyValueError::new_err(format!("Order {} not found", order_id)))
    }

    fn _transition(&self, order_id: String, event: String) -> PyResult<Order> {
        let mut orders = self.active_orders.write().unwrap();
        if let Some(order) = orders.get_mut(&order_id) {
            order.status = self.fsm.transition(order.status, event)?;
            return Ok(order.clone());
        }
        Err(pyo3::exceptions::PyValueError::new_err(format!("Order {} not found", order_id)))
    }

    pub fn get_active_orders(&self) -> HashMap<String, Order> {
        self.active_orders.read().unwrap().clone()
    }

    pub fn get_account(&self) -> Account {
        self.account.read().unwrap().clone()
    }
}
