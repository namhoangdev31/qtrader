use crate::algo::*;
use crate::oms::Side;

#[test]
fn test_twap_generates_slices() {
    let mut twap = TwapAlgo::new(100.0, 60000, 6, 0, 0); // 100 qty over 60s, 6 slices
    let orders = twap.generate_slices(10000, "BTC", &Side::Buy); // 10s in
    assert_eq!(orders.len(), 1); // 1 slice expected at 10s
    assert_eq!(twap.slices_executed, 1);
}

#[test]
fn test_twap_catches_up() {
    let mut twap = TwapAlgo::new(100.0, 60000, 6, 0, 0);
    // Jump to 50s — should catch up 5 slices
    let orders = twap.generate_slices(50000, "BTC", &Side::Buy);
    assert_eq!(orders.len(), 5);
    assert_eq!(twap.slices_executed, 5);
}

#[test]
fn test_twap_completes() {
    let mut twap = TwapAlgo::new(100.0, 60000, 6, 0, 0);
    twap.generate_slices(60000, "BTC", &Side::Buy);
    assert!(twap.is_complete());
    assert_eq!(twap.progress(), 1.0);
}
