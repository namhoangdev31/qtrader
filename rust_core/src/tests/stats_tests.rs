use crate::stats::*;

#[test]
fn test_historical_es() {
    let returns = vec![10.0, -5.0, 2.0, 0.0, -10.0, 5.0, 1.0, -2.0];
    let es = calculate_historical_es_logic(returns, 0.25);
    assert_eq!(es, -7.5);
}

#[test]
fn test_omega_ratio() {
    let returns = vec![0.02, 0.03, -0.01, -0.02, 0.01];
    let omega = calculate_omega_ratio_logic(returns, 0.0);
    assert!((omega - 2.0).abs() < 1e-12);
}

#[test]
fn test_sortino_ratio() {
    let returns = vec![0.01, 0.02, -0.01, -0.01];
    let sortino = calculate_sortino_ratio_logic(returns, 0.0, 1.0);
    assert!((sortino - 0.35355).abs() < 1e-4);
}

#[test]
fn test_calmar_ratio() {
    let calmar = calculate_calmar_ratio_logic(0.20, 0.10);
    assert_eq!(calmar, 2.0);
    let calmar_zero = calculate_calmar_ratio_logic(0.20, 0.00);
    assert_eq!(calmar_zero, 0.0);
}
