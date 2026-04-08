use crate::sizing::*;

#[test]
fn test_kelly_logic() {
    // Win rate = 0.6. Win loss = 1.0 (Even odds).
    let f = calculate_kelly_fraction_logic(0.6, 1.0, 0.5);
    assert!((f - 0.1).abs() < 1e-6);

    // Win rate = 0.5. Win loss = 2.0.
    let f2 = calculate_kelly_fraction_logic(0.5, 2.0, 0.5);
    assert!((f2 - 0.125).abs() < 1e-6);
    
    let f_neg = calculate_kelly_fraction_logic(0.4, 1.0, 0.5);
    assert_eq!(f_neg, 0.0);
}

#[test]
fn test_growth_optimal() {
    let returns = vec![0.1, 0.2, -0.1, -0.05];
    let f = calculate_growth_optimal_fraction_logic(returns, 1.0);
    assert!(f > 0.0);
    assert!(f <= 1.0);
}
