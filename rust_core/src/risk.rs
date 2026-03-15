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
