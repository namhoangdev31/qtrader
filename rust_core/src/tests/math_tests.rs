use crate::math::*;

#[test]
fn test_max_drawdown() {
    let engine = MathEngine::new();
    let equity = vec![100.0, 110.0, 90.0, 120.0, 80.0, 150.0];
    let (max_dd, peak) = engine.calculate_max_drawdown(equity);
    assert!((max_dd - 0.333333).abs() < 1e-4);
    assert_eq!(peak, 150.0);
}

#[test]
fn test_rolling_volatility() {
    let engine = MathEngine::new();
    let series = vec![1.0, 2.0, 3.0, 4.0, 5.0];
    let vol = engine.calculate_rolling_volatility(series, 2);
    assert_eq!(vol[1], 0.5);
    assert_eq!(vol[4], 0.5);
}
