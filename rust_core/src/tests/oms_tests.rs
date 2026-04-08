use crate::oms::*;
use std::collections::HashMap;

#[test]
fn test_position_add_fill_long() {
    let mut pos = Position::new("BTC".to_string());
    pos.add_fill(Side::Buy, 1.0, 50000.0);
    assert_eq!(pos.qty, 1.0);
    assert_eq!(pos.avg_entry_price, 50000.0);

    pos.add_fill(Side::Buy, 1.0, 60000.0);
    assert_eq!(pos.qty, 2.0);
    assert_eq!(pos.avg_entry_price, 55000.0);
}

#[test]
fn test_position_partial_close() {
    let mut pos = Position::new("BTC".to_string());
    pos.add_fill(Side::Buy, 2.0, 50000.0);
    pos.add_fill(Side::Sell, 1.0, 60000.0);
    assert_eq!(pos.qty, 1.0);
    assert_eq!(pos.avg_entry_price, 50000.0);
}

#[test]
fn test_account_equity() {
    let mut account = Account::new(100000.0);
    let prices = HashMap::new();

    assert_eq!(account.equity(prices), 100000.0);

    let mut btc_pos = Position::new("BTC".to_string());
    btc_pos.add_fill(Side::Buy, 1.0, 40000.0);
    account.positions.insert("BTC".to_string(), btc_pos);
    account.cash -= 40000.0;

    let mut prices2 = HashMap::new();
    prices2.insert("BTC".to_string(), 50000.0);
    assert_eq!(account.equity(prices2), 110000.0);
}

#[test]
fn test_position_shorting() {
    let mut pos = Position::new("ETH".to_string());
    pos.add_fill(Side::Sell, 10.0, 2000.0);
    assert_eq!(pos.qty, -10.0);
    assert_eq!(pos.avg_entry_price, 2000.0);

    pos.add_fill(Side::Sell, 10.0, 3000.0);
    assert_eq!(pos.qty, -20.0);
    assert_eq!(pos.avg_entry_price, 2500.0);
}

#[test]
fn test_position_full_close_and_flip() {
    let mut pos = Position::new("ETH".to_string());
    pos.add_fill(Side::Buy, 5.0, 2000.0);
    pos.add_fill(Side::Sell, 5.0, 2500.0);
    assert_eq!(pos.qty, 0.0);

    pos.add_fill(Side::Sell, 2.0, 2600.0);
    assert_eq!(pos.qty, -2.0);
    assert_eq!(pos.avg_entry_price, 2600.0);
}
