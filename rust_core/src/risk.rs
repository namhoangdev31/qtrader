use crate::oms::{Account, Order, Side};

pub struct RiskEngine {
    pub max_position_usd: f64,
    pub max_drawdown_pct: f64,
}

impl RiskEngine {
    pub fn new(max_position_usd: f64, max_drawdown_pct: f64) -> Self {
        RiskEngine {
            max_position_usd,
            max_drawdown_pct,
        }
    }

    /// Pre-trade risk check: true if order is allowed.
    pub fn check_order(
        &self,
        order: &Order,
        account: &Account,
        current_price: f64,
        peak_equity: f64,
    ) -> Result<(), String> {
        // 1. Max Drawdown check
        let mut mock_prices = std::collections::HashMap::new();
        mock_prices.insert(order.symbol.clone(), current_price);
        let curr_eq = account.equity(&mock_prices);

        if peak_equity > 0.0 {
            let dd = (peak_equity - curr_eq) / peak_equity;
            if dd > self.max_drawdown_pct {
                return Err(format!("Max drawdown exceeded: {:.2}%", dd * 100.0));
            }
        }

        // 2. Position Size Check
        let mut existing_qty = 0.0;
        if let Some(pos) = account.positions.get(&order.symbol) {
            existing_qty = pos.qty;
        }

        let signed_order_qty = match order.side {
            Side::Buy => order.qty,
            Side::Sell => -order.qty,
        };

        let new_qty = existing_qty + signed_order_qty;
        let pos_value = new_qty.abs() * current_price;

        if pos_value > self.max_position_usd {
            return Err(format!(
                "Position limit exceeded. Value: ${:.2}, Limit: ${:.2}",
                pos_value, self.max_position_usd
            ));
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_risk_engine_max_pos() {
        let risk = RiskEngine::new(1000.0, 0.1);
        let account = Account::new(10000.0);
        
        let order = Order::new(1, "BTC".to_string(), Side::Buy, 0.1, 0.0, crate::oms::OrderType::Market, 0);
        
        // Value = 0.1 * 11000 = 1100 > 1000. Reject.
        assert!(risk.check_order(&order, &account, 11000.0, 10000.0).is_err());
        
        // Value = 0.1 * 9000 = 900 < 1000. OK.
        assert!(risk.check_order(&order, &account, 9000.0, 10000.0).is_ok());
    }

    #[test]
    fn test_risk_engine_max_dd() {
        let risk = RiskEngine::new(100000.0, 0.1);
        let account = Account::new(10000.0); // Equity = 10000
        
        let order = Order::new(1, "BTC".to_string(), Side::Buy, 1.0, 0.0, crate::oms::OrderType::Market, 0);
        
        // Peak = 12000, current = 10000 -> dd = 16% > 10%. Reject.
        assert!(risk.check_order(&order, &account, 10000.0, 12000.0).is_err());
        
        // Peak = 10500, current = 10000 -> dd = 4.7% < 10%. OK.
        assert!(risk.check_order(&order, &account, 10000.0, 10500.0).is_ok());
    }

    #[test]
    fn test_risk_engine_zero_peak_equity() {
        // First trade, peak equity hasn't been established yet (0.0)
        let risk = RiskEngine::new(100000.0, 0.1);
        let account = Account::new(10000.0);
        let order = Order::new(1, "BTC".to_string(), Side::Buy, 0.5, 0.0, crate::oms::OrderType::Market, 0);
        
        // Should bypass max dd check and pass position check
        assert!(risk.check_order(&order, &account, 10000.0, 0.0).is_ok());
    }

    #[test]
    fn test_risk_engine_short_position_limit() {
        let risk = RiskEngine::new(20000.0, 0.1);
        let mut account = Account::new(50000.0);
        
        // Already short 1 BTC at 15000
        let mut pos = crate::oms::Position::new("BTC".to_string());
        pos.add_fill(Side::Sell, 1.0, 15000.0);
        account.positions.insert("BTC".to_string(), pos);
        
        // Try to short another 1 BTC at 15000 -> Total short value = 30000 > 20000 limit
        let order = Order::new(2, "BTC".to_string(), Side::Sell, 1.0, 0.0, crate::oms::OrderType::Market, 0);
        assert!(risk.check_order(&order, &account, 15000.0, 50000.0).is_err());
    }
}
