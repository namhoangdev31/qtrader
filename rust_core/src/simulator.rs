use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;
use std::collections::HashMap;

use crate::matching::MatchingEngine;
use crate::oms::{Account, Order, Side};
use crate::risk::RiskEngine;

#[pyclass]
#[derive(Clone)]
pub struct SimulatorConfig {
    #[pyo3(get, set)]
    pub initial_capital: f64,
    #[pyo3(get, set)]
    pub latency_ms: i64,
    #[pyo3(get, set)]
    pub fee_rate: f64,
    #[pyo3(get, set)]
    pub slippage_bps: f64,
    #[pyo3(get, set)]
    pub max_position_usd: f64,
    #[pyo3(get, set)]
    pub max_drawdown_pct: f64,
    #[pyo3(get, set)]
    pub max_leverage: f64,
    #[pyo3(get, set)]
    pub max_hhi: f64,
    #[pyo3(get, set)]
    pub daily_loss_limit: f64,
}

#[pymethods]
impl SimulatorConfig {
    #[new]
    #[pyo3(signature = (initial_capital, latency_ms, fee_rate, slippage_bps, max_position_usd, max_drawdown_pct, max_leverage=2.0, max_hhi=0.5, daily_loss_limit=50000.0))]
    pub fn new(
        initial_capital: f64,
        latency_ms: i64,
        fee_rate: f64,
        slippage_bps: f64,
        max_position_usd: f64,
        max_drawdown_pct: f64,
        max_leverage: f64,
        max_hhi: f64,
        daily_loss_limit: f64,
    ) -> Self {
        SimulatorConfig {
            initial_capital,
            latency_ms,
            fee_rate,
            slippage_bps,
            max_position_usd,
            max_drawdown_pct,
            max_leverage,
            max_hhi,
            daily_loss_limit,
        }
    }
}

/// Runs a high-fidelity tick-by-tick backtest for a single symbol.
/// Supports L1 book data for better fill accuracy.
#[pyfunction]
pub fn run_hft_simulation(
    py: Python<'_>,
    config: &SimulatorConfig,
    symbol: String,
    timestamps: PyReadonlyArray1<'_, i64>,
    bid_prices: PyReadonlyArray1<'_, f64>,
    ask_prices: PyReadonlyArray1<'_, f64>,
    bid_sizes: PyReadonlyArray1<'_, f64>,
    ask_sizes: PyReadonlyArray1<'_, f64>,
    signals: PyReadonlyArray1<'_, f64>, // 1.0=Buy, -1.0=Sell, 0.0=None
) -> PyResult<(Py<PyArray1<f64>>, f64)> {
    let mut account = Account::new(config.initial_capital);
    let matcher = MatchingEngine::new(config.latency_ms, config.fee_rate, config.slippage_bps);
    let mut risk = RiskEngine::new(
        config.max_position_usd, 
        config.max_drawdown_pct, 
        1000.0, 
        100000.0, 
        100, 
        0.05,
        config.max_leverage,
        config.max_hhi,
        config.daily_loss_limit,
    );

    let ts_slice = timestamps.as_slice()?;
    let bid_p = bid_prices.as_slice()?;
    let ask_p = ask_prices.as_slice()?;
    let bid_s = bid_sizes.as_slice()?;
    let ask_s = ask_sizes.as_slice()?;
    let sig_slice = signals.as_slice()?;

    let n = ts_slice.len();
    let mut equity_curve = Vec::with_capacity(n);
    let mut open_orders: HashMap<String, Order> = HashMap::new();
    let mut order_id_counter = 0;
    let mut peak_equity = config.initial_capital;

    for i in 0..n {
        let ts = ts_slice[i];
        let bid = bid_p[i];
        let ask = ask_p[i];
        let mid = (bid + ask) / 2.0;
        let sig = sig_slice[i];

        // 1. Match active orders using L1 liquidity if available
        // Simple filling logic: check if buy order price >= ask_price, sell <= bid_price
        let fills = matcher.match_orders(&mut open_orders, mid, ts);
        
        for (id, qty, fill_price, comm) in fills {
            if let Some(order) = open_orders.remove(&id) {
                account.cash -= comm;
                account.total_commissions += comm;
                
                match order.side {
                    Side::Buy => account.cash -= qty * fill_price,
                    Side::Sell => account.cash += qty * fill_price,
                }
                
                let pos = account.positions.entry(symbol.clone()).or_insert_with(|| crate::oms::Position::new(symbol.clone()));
                pos.add_fill(order.side, qty, fill_price);
            }
        }

        // 2. Track Equity using mid-price
        let mut sim_prices = HashMap::new();
        sim_prices.insert(symbol.clone(), mid);
        let current_eq = account.equity(sim_prices);
        equity_curve.push(current_eq);
        if current_eq > peak_equity { peak_equity = current_eq; }

        // 3. Execution Logic
        if sig != 0.0 && open_orders.is_empty() {
            let target_qty = (current_eq * 0.1) / mid; // Constant 10% sizing
            let side = if sig > 0.0 { Side::Buy } else { Side::Sell };
            let order_price = if sig > 0.0 { ask } else { bid }; // Aggressive market fill

            order_id_counter += 1;
            let order_id = order_id_counter.to_string();
            let order = Order::new(
                order_id.clone(), symbol.clone(), side, target_qty, order_price,
                crate::oms::OrderType::Market, ts
            );

            if risk.check_order(&order, &account, mid, peak_equity).is_ok() {
                open_orders.insert(order_id, order);
            }
        }
    }

    let eq_pyarray = pyo3::prelude::Py::from(numpy::PyArray1::from_vec(py, equity_curve));
    Ok((eq_pyarray, peak_equity))
}

/// Legacy 1D simulation for backwards compatibility
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
    let mut risk = RiskEngine::new(
        config.max_position_usd, 
        config.max_drawdown_pct, 
        1000.0, 
        100000.0, 
        100, 
        0.05,
        config.max_leverage,
        config.max_hhi,
        config.daily_loss_limit,
    );

    let ts_slice = timestamps.as_slice()?;
    let close_slice = closes.as_slice()?;
    let sig_slice = signals.as_slice()?;

    let n = ts_slice.len();
    let mut equity_curve = Vec::with_capacity(n);
    let mut open_orders: HashMap<String, Order> = HashMap::new();
    let mut order_id_counter = 0;
    let mut peak_equity = config.initial_capital;

    for i in 0..n {
        let ts = ts_slice[i];
        let price = close_slice[i];
        let sig = sig_slice[i];

        let fills = matcher.match_orders(&mut open_orders, price, ts);
        for (id, qty, fill_price, comm) in fills {
            if let Some(order) = open_orders.remove(&id) {
                account.cash -= comm;
                match order.side {
                    Side::Buy => account.cash -= qty * fill_price,
                    Side::Sell => account.cash += qty * fill_price,
                }
                let pos = account.positions.entry(symbol.clone()).or_insert_with(|| crate::oms::Position::new(symbol.clone()));
                pos.add_fill(order.side, qty, fill_price);
            }
        }

        let mut sim_prices = HashMap::new();
        sim_prices.insert(symbol.clone(), price);
        let current_eq = account.equity(sim_prices);
        equity_curve.push(current_eq);
        if current_eq > peak_equity { peak_equity = current_eq; }

        if sig != 0.0 && open_orders.is_empty() {
            let qty = (current_eq * 0.1) / price;
            let side = if sig > 0.0 { Side::Buy } else { Side::Sell };
            order_id_counter += 1;
            let order_id = order_id_counter.to_string();
            let order = Order::new(order_id.clone(), symbol.clone(), side, qty, 0.0, crate::oms::OrderType::Market, ts);
            if risk.check_order(&order, &account, price, peak_equity).is_ok() {
                open_orders.insert(order_id, order);
            }
        }
    }

    let eq_pyarray = pyo3::prelude::Py::from(numpy::PyArray1::from_vec(py, equity_curve));
    Ok((eq_pyarray, peak_equity))
}
