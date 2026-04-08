use crate::oms::{Account, Order, Side};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::VecDeque;
use std::time::{SystemTime, UNIX_EPOCH};

#[pyclass]
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum WarModeState {
    Normal,
    WarMode,
    Halted,
}

#[pyclass]
pub struct RiskEngine {
    pub core: RiskCore,
}

#[pymethods]
impl RiskEngine {
    #[new]
    #[pyo3(signature = (
        max_position_usd, 
        max_drawdown_pct, 
        max_order_qty=100.0, 
        max_order_notional=10000.0, 
        max_orders_per_second=10, 
        max_price_deviation_pct=0.03,
        max_leverage=2.0,
        max_hhi=0.5,
        daily_loss_limit=50000.0
    ))]
    pub fn new(
        max_position_usd: f64,
        max_drawdown_pct: f64,
        max_order_qty: f64,
        max_order_notional: f64,
        max_orders_per_second: usize,
        max_price_deviation_pct: f64,
        max_leverage: f64,
        max_hhi: f64,
        daily_loss_limit: f64,
    ) -> Self {
        RiskEngine {
            core: RiskCore::new(
                max_position_usd,
                max_drawdown_pct,
                max_order_qty,
                max_order_notional,
                max_orders_per_second,
                max_price_deviation_pct,
                max_leverage,
                max_hhi,
                daily_loss_limit,
            ),
        }
    }

    pub fn check_order(&mut self, order: &Order, account: &Account, current_price: f64, peak_equity: f64) -> PyResult<()> {
        self.core.check_order(order, account, current_price, peak_equity)
            .map_err(|e| PyValueError::new_err(e))
    }

    pub fn check_portfolio_state(&mut self, current_equity: f64, peak_equity: f64, gross_exposure: f64) -> PyResult<()> {
        self.core.check_portfolio_state(current_equity, peak_equity, gross_exposure)
            .map_err(|e| PyValueError::new_err(e))
    }

    pub fn get_state(&self) -> WarModeState {
        self.core.state
    }
}

// --- Standalone Logic Core ---

pub struct RiskCore {
    // Limits
    pub max_position_usd: f64,
    pub max_drawdown_pct: f64,
    pub max_order_qty: f64,
    pub max_order_notional: f64,
    pub max_orders_per_second: usize,
    pub max_price_deviation_pct: f64,
    pub max_leverage: f64,
    pub max_hhi: f64,
    pub daily_loss_limit: f64,

    // State
    pub state: WarModeState,
    pub order_timestamps: VecDeque<u128>,
}

impl RiskCore {
    pub fn new(
        max_position_usd: f64, 
        max_drawdown_pct: f64, 
        max_order_qty: f64, 
        max_order_notional: f64, 
        max_orders_per_second: usize, 
        max_price_deviation_pct: f64,
        max_leverage: f64,
        max_hhi: f64,
        daily_loss_limit: f64,
    ) -> Self {
        RiskCore {
            max_position_usd, 
            max_drawdown_pct, 
            max_order_qty, 
            max_order_notional, 
            max_orders_per_second, 
            max_price_deviation_pct,
            max_leverage,
            max_hhi,
            daily_loss_limit,
            state: WarModeState::Normal,
            order_timestamps: VecDeque::new(),
        }
    }

    pub fn check_portfolio_state(&mut self, current_equity: f64, peak_equity: f64, gross_exposure: f64) -> Result<(), String> {
        if self.state == WarModeState::Halted {
            return Err("SYSTEM_HALTED: Kill switch active".to_string());
        }

        // Drawdown
        if peak_equity > 0.0 {
            let dd = (peak_equity - current_equity) / peak_equity;
            if dd > self.max_drawdown_pct {
                self.state = WarModeState::Halted;
                return Err(format!("CRITICAL_DRAWDOWN: {:.2}% > {:.2}%", dd * 100.0, self.max_drawdown_pct * 100.0));
            }
        }

        // Leverage
        let leverage = gross_exposure / current_equity;
        if leverage > self.max_leverage {
            return Err(format!("LEVERAGE_EXCEEDED: {:.2} > {:.2}", leverage, self.max_leverage));
        }

        Ok(())
    }

    pub fn check_order(&mut self, order: &Order, account: &Account, current_price: f64, peak_equity: f64) -> Result<(), String> {
        if self.state == WarModeState::Halted {
            return Err("SYSTEM_HALTED: Kill switch active".to_string());
        }

        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_millis();
        self.order_timestamps.retain(|&ts| now - ts < 1000);
        if self.order_timestamps.len() >= self.max_orders_per_second {
            return Err(format!("Rate limit exceeded: {}/s", self.max_orders_per_second));
        }

        // 1. War Mode restrictions
        if self.state == WarModeState::WarMode {
            // Only allow unwinding or hedging (simplified check: reduction in position abs(qty))
            let existing_qty = account.positions.get(&order.symbol).map(|p| p.qty).unwrap_or(0.0);
            let signed_order_qty = match order.side { Side::Buy => order.qty, Side::Sell => -order.qty };
            if (existing_qty + signed_order_qty).abs() >= existing_qty.abs() && existing_qty != 0.0 {
                return Err("WAR_MODE: Only position reduction (unwind/hedge) allowed".to_string());
            }
            if existing_qty == 0.0 {
                return Err("WAR_MODE: New positions blocked".to_string());
            }
        }

        // 2. Fat-finger checks
        if order.qty > self.max_order_qty {
            return Err(format!("Qty {} > {}", order.qty, self.max_order_qty));
        }
        let notional = order.qty * current_price;
        if notional > self.max_order_notional {
            return Err(format!("Notional ${:.2} > ${:.2}", notional, self.max_order_notional));
        }
        let dev = (order.price - current_price).abs() / current_price;
        if order.price > 0.0 && dev > self.max_price_deviation_pct {
            return Err(format!("Dev {:.2}% > {:.2}%", dev * 100.0, self.max_price_deviation_pct * 100.0));
        }

        // 3. Portfolio limits
        let mut mock_prices = std::collections::HashMap::new();
        mock_prices.insert(order.symbol.clone(), current_price);
        let curr_eq = account.equity_internal(&mock_prices);
        
        // Drawdown
        if peak_equity > 0.0 {
            let dd = (peak_equity - curr_eq) / peak_equity;
            if dd > self.max_drawdown_pct {
                self.state = WarModeState::Halted;
                return Err(format!("CRITICAL_DRAWDOWN: {:.2}% > {:.2}%", dd * 100.0, self.max_drawdown_pct * 100.0));
            }
        }

        // Leverage & Concentration
        let gross_exposure = account.positions.values().map(|p| p.qty.abs() * current_price).sum::<f64>() + notional;
        let leverage = gross_exposure / curr_eq;
        if leverage > self.max_leverage {
            return Err(format!("LEVERAGE_EXCEEDED: {:.2} > {:.2}", leverage, self.max_leverage));
        }

        // Position limit
        let existing_qty = account.positions.get(&order.symbol).map(|p| p.qty).unwrap_or(0.0);
        let signed_order_qty = match order.side { Side::Buy => order.qty, Side::Sell => -order.qty };
        let pos_value = (existing_qty + signed_order_qty).abs() * current_price;
        if pos_value > self.max_position_usd {
            return Err(format!("POS_LIMIT_EXCEEDED: ${:.2} > ${:.2}", pos_value, self.max_position_usd));
        }

        self.order_timestamps.push_back(now); 
        Ok(())
    }

    pub fn check_order_simple(&self, is_buy: bool, order_qty: f64, current_price: f64, existing_position_qty: f64) -> Result<(), String> {
        if self.state == WarModeState::Halted {
            return Err("HALTED".to_string());
        }
        let signed_order_qty = if is_buy { order_qty } else { -order_qty };
        let pos_value = (existing_position_qty + signed_order_qty).abs() * current_price;
        if pos_value > self.max_position_usd {
            return Err(format!("Pos limit ${:.2} exceeded", pos_value));
        }
        Ok(())
    }
}
