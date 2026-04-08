#[cfg(test)]
mod tests {
    use crate::execution::ExecutionEngine;
    use crate::risk::{RiskEngine, WarModeState};
    use crate::oms::{Account, Order, OrderType, Side};
    use crate::router::RoutingMode;
    use std::collections::HashMap;

    #[test]
    fn test_execution_engine_basic() {
        let risk = RiskEngine::new(
            100000.0, // max_position_usd
            0.1,      // max_drawdown_pct
            1000.0,   // max_order_qty
            10000.0,  // max_order_notional
            10,       // max_orders_per_second
            0.05,     // max_price_deviation_pct
            2.0,      // max_leverage
            0.5,      // max_hhi
            50000.0,  // daily_loss_limit
        );
        
        let mut engine = ExecutionEngine::new(&risk, RoutingMode::Smart, 3);
        let account = Account::new(1000000.0);
        let order = Order::new(1, "BTC/USDT".to_string(), Side::Buy, 0.1, 50000.0, OrderType::Limit, 1000);
        
        let mut market_data = HashMap::new();
        market_data.insert("BINANCE".to_string(), (49990.0, 50010.0));
        
        let result = engine.execute_order(order, &account, 50000.0, 1000000.0, market_data);
        assert!(result.is_ok());
        let routed = result.unwrap();
        assert_eq!(routed.len(), 1);
        assert_eq!(routed[0].1, "BINANCE");
    }

    #[test]
    fn test_risk_rejection() {
        let risk = RiskEngine::new(
            1000.0,   // max_position_usd (very low)
            0.1,
            1000.0,
            10000.0,
            10,
            0.05,
            2.0,
            0.5,
            50000.0,
        );
        
        let mut engine = ExecutionEngine::new(&risk, RoutingMode::Smart, 3);
        let account = Account::new(1000000.0);
        // Order value $5000 > $1000 limit
        let order = Order::new(1, "BTC/USDT".to_string(), Side::Buy, 0.1, 50000.0, OrderType::Limit, 1000);
        
        let mut market_data = HashMap::new();
        market_data.insert("BINANCE".to_string(), (49990.0, 50010.0));
        
        let result = engine.execute_order(order, &account, 50000.0, 1000000.0, market_data);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("Risk Check Failed"));
    }
}
