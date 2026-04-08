use crate::matching::*;
use crate::oms::{Order, OrderType, Side};
use std::collections::HashMap;

#[test]
fn test_matching_engine_market_order() {
    let matching = MatchingEngine::new(0, 0.0005, 10.0);
    let mut orders = HashMap::new();
    let order = Order::new(
        1,
        "BTC".to_string(),
        Side::Buy,
        1.0,
        0.0,
        OrderType::Market,
        1000,
    );
    orders.insert(1, order);

    let fills = matching.match_orders(&mut orders, 50000.0, 2000);
    assert_eq!(fills.len(), 1);
    let (_, qty, price, comm) = fills[0];
    assert_eq!(qty, 1.0);
    assert_eq!(price, 50000.0 * 1.001);
    assert_eq!(comm, price * qty * 0.0005);
}

#[test]
fn test_matching_engine_limit_order() {
    let matching = MatchingEngine::new(0, 0.0, 0.0);
    let mut orders = HashMap::new();
    let buy_order = Order::new(
        1,
        "BTC".to_string(),
        Side::Buy,
        1.0,
        49000.0,
        OrderType::Limit,
        1000,
    );
    orders.insert(1, buy_order);

    let fills_1 = matching.match_orders(&mut orders, 50000.0, 2000);
    assert_eq!(fills_1.len(), 0);

    let fills_2 = matching.match_orders(&mut orders, 48000.0, 3000);
    assert_eq!(fills_2.len(), 1);
    assert_eq!(fills_2[0].2, 48000.0);
}

#[test]
fn test_matching_engine_latency() {
    let matching = MatchingEngine::new(100, 0.0, 0.0);
    let mut orders = HashMap::new();
    let order = Order::new(
        1,
        "BTC".to_string(),
        Side::Buy,
        1.0,
        0.0,
        OrderType::Market,
        1000,
    );
    orders.insert(1, order);

    let fills_1 = matching.match_orders(&mut orders, 50000.0, 1050);
    assert_eq!(fills_1.len(), 0);

    let fills_2 = matching.match_orders(&mut orders, 50000.0, 1100);
    assert_eq!(fills_2.len(), 1);
}

#[test]
fn test_matching_engine_slippage() {
    let matching = MatchingEngine::new(0, 0.0, 100.0);
    let mut orders = HashMap::new();
    let buy_order = Order::new(
        1,
        "BTC".to_string(),
        Side::Buy,
        1.0,
        0.0,
        OrderType::Market,
        1000,
    );
    orders.insert(1, buy_order);
    let sell_order = Order::new(
        2,
        "BTC".to_string(),
        Side::Sell,
        1.0,
        0.0,
        OrderType::Market,
        1000,
    );
    orders.insert(2, sell_order);

    let fills = matching.match_orders(&mut orders, 50000.0, 2000);
    assert_eq!(fills.len(), 2);
    for fill in fills {
        if fill.0 == 1 {
            assert_eq!(fill.2, 50500.0);
        } else if fill.0 == 2 {
            assert_eq!(fill.2, 49500.0);
        }
    }
}
