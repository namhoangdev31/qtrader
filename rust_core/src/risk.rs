use crate::oms::{Account, Order, Side};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyclass]
pub struct RiskEngine {
    #[pyo3(get, set)]
    pub max_position_usd: f64,
    #[pyo3(get, set)]
    pub max_drawdown_pct: f64,
}

#[pymethods]
impl RiskEngine {
    #[new]
    pub fn new(max_position_usd: f64, max_drawdown_pct: f64) -> Self {
        RiskEngine {
            max_position_usd,
            max_drawdown_pct,
        }
    }

    /// Pre-trade risk check: returns Ok(()) if order is allowed, raises ValueError if rejected.
    pub fn check_order(
        &self,
        order: &Order,
        account: &Account,
        current_price: f64,
        peak_equity: f64,
    ) -> PyResult<()> {
        // 1. Max Drawdown check
        let mut mock_prices = std::collections::HashMap::new();
        mock_prices.insert(order.symbol.clone(), current_price);
        let curr_eq = account.equity_internal(&mock_prices);

        if peak_equity > 0.0 {
            let dd = (peak_equity - curr_eq) / peak_equity;
            if dd > self.max_drawdown_pct {
                return Err(PyValueError::new_err(format!(
                    "Max drawdown exceeded: {:.2}%",
                    dd * 100.0
                )));
            }
        }

        // 2. Position Size Check
        let existing_qty = account
            .positions
            .get(&order.symbol)
            .map(|p| p.qty)
            .unwrap_or(0.0);

        let signed_order_qty = match order.side {
            Side::Buy => order.qty,
            Side::Sell => -order.qty,
        };

        let new_qty = existing_qty + signed_order_qty;
        let pos_value = new_qty.abs() * current_price;

        if pos_value > self.max_position_usd {
            return Err(PyValueError::new_err(format!(
                "Position limit exceeded. Value: ${:.2}, Limit: ${:.2}",
                pos_value, self.max_position_usd
            )));
        }

        Ok(())
    }

    /// Simplified check without Account — accepts individual parameters.
    pub fn check_order_simple(
        &self,
        is_buy: bool,
        order_qty: f64,
        _symbol: &str,
        current_price: f64,
        existing_position_qty: f64,
    ) -> PyResult<()> {
        let signed_order_qty = if is_buy { order_qty } else { -order_qty };
        let new_qty = existing_position_qty + signed_order_qty;
        let pos_value = new_qty.abs() * current_price;

        if pos_value > self.max_position_usd {
            return Err(PyValueError::new_err(format!(
                "Position limit exceeded. Value: ${:.2}, Limit: ${:.2}",
                pos_value, self.max_position_usd
            )));
        }

        Ok(())
    }

    fn __repr__(&self) -> String {
        format!(
            "RiskEngine(max_position_usd={}, max_drawdown_pct={})",
            self.max_position_usd, self.max_drawdown_pct
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::oms::OrderType;

    #[test]
    fn test_risk_engine_max_pos() {
        let risk = RiskEngine::new(1000.0, 0.1);
        let account = Account::new(10000.0);
        let order = Order::new(
            1,
            "BTC".to_string(),
            Side::Buy,
            0.1,
            0.0,
            OrderType::Market,
            0,
        );
        assert!(risk
            .check_order(&order, &account, 11000.0, 10000.0)
            .is_err());
        assert!(risk.check_order(&order, &account, 9000.0, 10000.0).is_ok());
    }

    #[test]
    fn test_risk_engine_max_dd() {
        let risk = RiskEngine::new(100000.0, 0.1);
        let account = Account::new(10000.0);
        let order = Order::new(
            1,
            "BTC".to_string(),
            Side::Buy,
            1.0,
            0.0,
            OrderType::Market,
            0,
        );
        assert!(risk
            .check_order(&order, &account, 10000.0, 12000.0)
            .is_err());
        assert!(risk.check_order(&order, &account, 10000.0, 10500.0).is_ok());
    }

    #[test]
    fn test_risk_engine_zero_peak_equity() {
        let risk = RiskEngine::new(100000.0, 0.1);
        let account = Account::new(10000.0);
        let order = Order::new(
            1,
            "BTC".to_string(),
            Side::Buy,
            0.5,
            0.0,
            OrderType::Market,
            0,
        );
        assert!(risk.check_order(&order, &account, 10000.0, 0.0).is_ok());
    }

    #[test]
    fn test_risk_engine_short_position_limit() {
        let risk = RiskEngine::new(20000.0, 0.1);
        let mut account = Account::new(50000.0);
        let mut pos = crate::oms::Position::new("BTC".to_string());
        pos.add_fill(Side::Sell, 1.0, 15000.0);
        account.positions.insert("BTC".to_string(), pos);
        let order = Order::new(
            2,
            "BTC".to_string(),
            Side::Sell,
            1.0,
            0.0,
            OrderType::Market,
            0,
        );
        assert!(risk
            .check_order(&order, &account, 15000.0, 50000.0)
            .is_err());
    }
}
