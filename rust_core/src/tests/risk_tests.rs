use crate::risk::*;
use crate::oms::{Account, Order, OrderType, Side};

#[test]
fn test_risk_fat_finger() {
    let mut core = RiskCore::new(100000.0, 0.2, 100.0, 10000.0, 10, 0.05, 2.0, 0.5, 50000.0);
    let account = Account::new(100000.0);
    let order_qty = Order::new("1".to_string(), "BTC".to_string(), Side::Buy, 101.0, 50000.0, OrderType::Limit, 1000);
    assert!(core.check_order(&order_qty, &account, 50000.0, 100000.0).is_err());
    let order_notional = Order::new("2".to_string(), "BTC".to_string(), Side::Buy, 0.5, 50000.0, OrderType::Limit, 1000);
    assert!(core.check_order(&order_notional, &account, 50000.0, 100000.0).is_err());
}

#[test]
fn test_risk_position_limit() {
    let mut core = RiskCore::new(1000.0, 0.2, 100.0, 10000.0, 10, 0.05, 2.0, 0.5, 50000.0);
    let mut account = Account::new(10000.0);
    let order_1 = Order::new("1".to_string(), "BTC".to_string(), Side::Buy, 0.01, 50000.0, OrderType::Limit, 1000);
    assert!(core.check_order(&order_1, &account, 50000.0, 10000.0).is_ok());
    account.add_position_direct("BTC".to_string(), 0.01, 50000.0);
    let order_2 = Order::new("2".to_string(), "BTC".to_string(), Side::Buy, 0.02, 50000.0, OrderType::Limit, 1000);
    assert!(core.check_order(&order_2, &account, 50000.0, 10000.0).is_err());
}
