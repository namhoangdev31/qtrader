use crate::microstructure::*;

#[test]
fn test_imbalance_logic() {
    let core = MicrostructureCore::new(10);
    let imb = core.calculate_imbalance(100.0, 50.0);
    assert!((imb - 0.333333).abs() < 1e-4);
}

#[test]
fn test_microprice_logic() {
    let core = MicrostructureCore::new(10);
    let mp = core.calculate_microprice(100.0, 101.0, 10.0, 90.0);
    assert_eq!(mp, 100.1);
}

#[test]
fn test_vpin_rolling() {
    let mut core = MicrostructureCore::new(3);
    assert_eq!(core.update_vpin(1, 100.0), 1.0);
    assert_eq!(core.update_vpin(-1, 100.0), 0.0);
    assert_eq!(core.update_vpin(1, 50.0), 0.2);
}
