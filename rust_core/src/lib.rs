use pyo3::prelude::*;

pub mod algo;
pub mod matching;
pub mod oms;
pub mod risk;
pub mod simulator;

use crate::algo::TwapAlgo;
use crate::matching::MatchingEngine;
use crate::oms::{Account, Order, OrderStatus, OrderType, Position, Side};
use crate::risk::RiskEngine;
use crate::simulator::{run_simulation_1d, SimulatorConfig};

/// A Python module implemented in Rust.
#[pymodule]
fn qtrader_core(_py: Python, m: &PyModule) -> PyResult<()> {
    // OMS types
    m.add_class::<Side>()?;
    m.add_class::<OrderType>()?;
    m.add_class::<OrderStatus>()?;
    m.add_class::<Order>()?;
    m.add_class::<Position>()?;
    m.add_class::<Account>()?;

    // Execution types
    m.add_class::<MatchingEngine>()?;
    m.add_class::<TwapAlgo>()?;

    // Risk types
    m.add_class::<RiskEngine>()?;

    // Simulator types
    m.add_class::<SimulatorConfig>()?;
    m.add_function(wrap_pyfunction!(run_simulation_1d, m)?)?;

    Ok(())
}
