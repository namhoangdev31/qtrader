use crate::oms::{Account, Position};
use pyo3::prelude::*;
use std::collections::HashMap;

/// Result of NAV calculation.
#[pyclass]
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct NAVReport {
    #[pyo3(get)]
    pub nav: f64,
    #[pyo3(get)]
    pub cash: f64,
    #[pyo3(get)]
    pub realized_pnl: f64,
    #[pyo3(get)]
    pub unrealized_pnl: f64,
    #[pyo3(get)]
    pub total_fees: f64,
    #[pyo3(get)]
    pub maker_fees: f64,
    #[pyo3(get)]
    pub taker_fees: f64,
    #[pyo3(get)]
    pub funding_fees: f64,
    #[pyo3(get)]
    pub total_market_value: f64,
}

#[pymethods]
impl NAVReport {
    fn __repr__(&self) -> String {
        format!(
            "NAVReport(nav={:.2}, cash={:.2}, unrealized_pnl={:.2}, total_fees={:.2} [M:{:.2}/T:{:.2}/F:{:.2}])",
            self.nav, self.cash, self.unrealized_pnl, self.total_fees, self.maker_fees, self.taker_fees, self.funding_fees
        )
    }
}

/// Core Portfolio Engine for accounting and performance tracking.
#[pyclass]
pub struct PortfolioEngine;

#[pymethods]
impl PortfolioEngine {
    #[new]
    pub fn new() -> Self {
        PortfolioEngine
    }

    /// Computes Net Asset Value (NAV) and PnL breakdown.
    #[pyo3(signature = (account, mark_prices, total_fees=0.0, maker_fees=0.0, taker_fees=0.0, funding_fees=0.0))]
    pub fn compute_nav(
        &self,
        account: &Account,
        mark_prices: HashMap<String, f64>,
        total_fees: f64,
        maker_fees: f64,
        taker_fees: f64,
        funding_fees: f64,
    ) -> NAVReport {
        let mut total_market_value = 0.0;
        let mut total_unrealized_pnl = 0.0;

        for (symbol, pos) in &account.positions {
            let price = mark_prices
                .get(symbol)
                .copied()
                .unwrap_or(pos.avg_entry_price);
            let market_value = pos.qty * price;
            total_market_value += market_value;

            if pos.qty.abs() > 1e-9 {
                total_unrealized_pnl += pos.qty * (price - pos.avg_entry_price);
            }
        }

        let nav = account.cash + total_market_value - total_fees;

        NAVReport {
            nav,
            cash: account.cash,
            realized_pnl: 0.0,
            unrealized_pnl: total_unrealized_pnl,
            total_fees,
            maker_fees,
            taker_fees,
            funding_fees,
            total_market_value,
        }
    }

    pub fn is_withdrawal_eligible(&self, account: &Account) -> bool {
        account.positions.is_empty() || account.positions.values().all(|p| p.qty.abs() < 1e-9)
    }
}

/// Ledger entry for transactions.
#[pyclass(name = "LedgerEntry")]
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PortfolioLedgerEntry {
    #[pyo3(get, set)]
    pub tx_id: String,
    #[pyo3(get, set)]
    pub asset: String,
    #[pyo3(get, set)]
    pub amount: f64,
    #[pyo3(get, set)]
    pub entry_type: String,
}

#[pymethods]
impl PortfolioLedgerEntry {
    #[new]
    pub fn new(tx_id: String, asset: String, amount: f64, entry_type: String) -> Self {
        PortfolioLedgerEntry {
            tx_id,
            asset,
            amount,
            entry_type,
        }
    }
}

/// Atomic Transaction grouping multiple entries.
#[pyclass]
#[derive(Debug, Clone)]
pub struct Transaction {
    #[pyo3(get)]
    pub entries: Vec<PortfolioLedgerEntry>,
}

#[pymethods]
impl Transaction {
    #[new]
    pub fn new(entries: Vec<PortfolioLedgerEntry>) -> Self {
        Transaction { entries }
    }

    pub fn validate(&self) -> bool {
        let sum: f64 = self.entries.iter().map(|e| e.amount).sum();
        sum.abs() < 1e-10
    }
}

#[pyclass]
pub struct LedgerEngine {
    pub transactions: Vec<Transaction>,
}

#[pymethods]
impl LedgerEngine {
    #[new]
    pub fn new() -> Self {
        LedgerEngine {
            transactions: Vec::new(),
        }
    }

    pub fn record_transaction(&mut self, tx: Transaction) -> PyResult<bool> {
        use crate::persistence::{PersistenceTask, PersistenceWorker};

        if !tx.validate() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "LEDGER_CRITICAL | Transaction is unbalanced.",
            ));
        }

        let worker = PersistenceWorker::global();
        for entry in &tx.entries {
            worker.submit(PersistenceTask::RecordTransaction {
                tx_id: entry.tx_id.clone(),
                description: "N/A".to_string(),
                asset: entry.asset.clone(),
                amount: entry.amount,
                entry_type: entry.entry_type.clone(),
            });
        }

        self.transactions.push(tx);
        Ok(true)
    }

    pub fn get_balance(&self, asset: &str) -> f64 {
        self.transactions
            .iter()
            .flat_map(|tx| &tx.entries)
            .filter(|e| e.asset == asset)
            .map(|e| e.amount)
            .sum()
    }

    pub fn clear(&mut self) {
        self.transactions.clear();
    }
}
