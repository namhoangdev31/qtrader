use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;
use std::collections::HashMap;

use crate::matching::MatchingEngine;
use crate::oms::{Account, Order, Side};
use crate::risk::RiskEngine;

#[pyclass]
pub struct SimulatorConfig {
    pub initial_capital: f64,
    pub latency_ms: i64,
    pub fee_rate: f64,
    pub slippage_bps: f64,
    pub max_position_usd: f64,
    pub max_drawdown_pct: f64,
}

#[pymethods]
impl SimulatorConfig {
    #[new]
    pub fn new(
        initial_capital: f64,
        latency_ms: i64,
        fee_rate: f64,
        slippage_bps: f64,
        max_position_usd: f64,
        max_drawdown_pct: f64,
    ) -> Self {
        SimulatorConfig {
            initial_capital,
            latency_ms,
            fee_rate,
            slippage_bps,
            max_position_usd,
            max_drawdown_pct,
        }
    }
}

/// Runs a fast, purely numeric backtest against provided 1D arrays for a single symbol.
#[pyfunction]
pub fn run_simulation_1d(
    py: Python<'_>,
    config: &SimulatorConfig,
    symbol: String,
    timestamps: PyReadonlyArray1<'_, i64>,
    closes: PyReadonlyArray1<'_, f64>,
    signals: PyReadonlyArray1<'_, f64>,
) -> PyResult<(Py<PyArray1<f64>>, f64)> {
    let mut account = Account::new(config.initial_capital);
    let matcher = MatchingEngine::new(config.latency_ms, config.fee_rate, config.slippage_bps);
    let risk = RiskEngine::new(config.max_position_usd, config.max_drawdown_pct);

    let ts_slice = timestamps.as_slice()?;
    let close_slice = closes.as_slice()?;
    let sig_slice = signals.as_slice()?;

    let n = ts_slice.len();
    let mut equity_curve = Vec::with_capacity(n);

    let mut open_orders: HashMap<u64, Order> = HashMap::new();
    let mut order_id_counter = 0;

    let mut peak_equity = config.initial_capital;

    for i in 0..n {
        let ts = ts_slice[i];
        let price = close_slice[i];
        let sig = sig_slice[i];

        // 1. Match active orders first using current price
        let fills = matcher.match_orders(&mut open_orders, price, ts);

        for (id, qty, fill_price, comm) in fills {
            let side = open_orders.get(&id).unwrap().side;
            account.cash -= comm;
            account.total_commissions += comm;

            // Deduct cost of position
            match side {
                Side::Buy => {
                    account.cash -= qty * fill_price;
                }
                Side::Sell => {
                    account.cash += qty * fill_price;
                }
            }

            let pos = account
                .positions
                .entry(symbol.clone())
                .or_insert_with(|| crate::oms::Position::new(symbol.clone()));
            pos.add_fill(side, qty, fill_price);

            open_orders.remove(&id);
        }

        // 2. Track Equity
        let mut sim_prices = HashMap::new();
        sim_prices.insert(symbol.clone(), price);
        let current_eq = account.equity(sim_prices);
        equity_curve.push(current_eq);

        if current_eq > peak_equity {
            peak_equity = current_eq;
        }

        // 3. Generate new orders from signals (Simple Strategy logic here for simulation)
        // Signal logic: 1.0 = Buy 10%, -1.0 = Sell 10% of equity
        if sig != 0.0 && open_orders.is_empty() {
            let target_value = current_eq * 0.10; // Fixed simplistic sizing for now
            let qty = target_value / price;

            let side = if sig > 0.0 { Side::Buy } else { Side::Sell };

            order_id_counter += 1;
            let order = Order::new(
                order_id_counter,
                symbol.clone(),
                side,
                qty,
                0.0,
                crate::oms::OrderType::Market,
                ts,
            );

            // Risk Check
            if risk
                .check_order(&order, &account, price, peak_equity)
                .is_ok()
            {
                open_orders.insert(order_id_counter, order);
            }
        }
    }

    let final_eq = equity_curve.last().copied().unwrap_or(account.cash);

    // Convert output to PyArray
    let eq_pyarray = pyo3::prelude::Py::from(numpy::PyArray1::from_vec(py, equity_curve));

    Ok((eq_pyarray, final_eq))
}
