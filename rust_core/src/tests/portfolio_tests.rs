#[cfg(test)]
mod tests {
    use crate::portfolio::{PortfolioEngine, NAVReport};
    use crate::allocator::CapitalAllocator;
    use crate::oms::{Account, Position, Side};
    use std::collections::HashMap;

    #[test]
    fn test_nav_computation() {
        let engine = PortfolioEngine::new();
        let mut account = Account::new(10000.0);
        account.cash = 5000.0;
        
        let mut pos = Position::new("BTC".to_string());
        pos.qty = 1.0;
        pos.avg_entry_price = 45000.0;
        account.set_position("BTC".to_string(), pos);

        let mut mark_prices = HashMap::new();
        mark_prices.insert("BTC".to_string(), 46000.0);

        let report = engine.compute_nav(&account, mark_prices, 100.0, 0.0, 100.0, 0.0);

        // NAV = Cash(5000) + MV(46000) - Fees(100) = 50900
        assert_eq!(report.nav, 50900.0);
        assert_eq!(report.unrealized_pnl, 1000.0);
    }

    #[test]
    fn test_sharpe_allocation() {
        let allocator = CapitalAllocator::new(0.4); // 40% cap
        let mut strategies = HashMap::new();
        strategies.insert("strat1".to_string(), 3.0);
        strategies.insert("strat2".to_string(), 1.0);
        strategies.insert("strat3".to_string(), 1.0);

        let report = allocator.allocate_sharpe(strategies, 100000.0);

        assert_eq!(report.status, "ALLOCATION_COMPLETE");
        // Total Sharpe = 5. Weights = [0.6, 0.2, 0.2]
        // Cap strat1 to 0.4. Excess = 0.2. 
        // Redistribute 0.2 to strat2, strat3 (proportional to 0.2, 0.2 -> split 50/50).
        // Strat2 = 0.2 + 0.1 = 0.3. Strat3 = 0.2 + 0.1 = 0.3.
        // Final weights: {strat1: 0.4, strat2: 0.3, strat3: 0.3}
        assert_eq!(*report.weights.get("strat1").unwrap(), 0.4);
        assert_eq!(*report.weights.get("strat2").unwrap(), 0.3);
        assert_eq!(*report.weights.get("strat3").unwrap(), 0.3);
    }
}
