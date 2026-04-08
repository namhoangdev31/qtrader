use pyo3::prelude::*;

pub mod algo;
pub mod matching;
pub mod math;
pub mod microstructure;
pub mod oms;
pub mod risk;
pub mod simulator;
pub mod sizing;
pub mod stats;

#[cfg(test)]
mod tests;

use crate::algo::TwapAlgo;
use crate::matching::MatchingEngine;
use crate::math::MathEngine;
use crate::microstructure::MicrostructureEngine;
use crate::oms::{Account, Order, OrderStatus, OrderType, Position, Side};
use crate::risk::{RiskEngine, WarModeState};
use crate::simulator::{run_hft_simulation, run_simulation_1d, SimulatorConfig};
use crate::sizing::SizingEngine;
use crate::stats::StatsEngine;

/// A Python module implemented in Rust.
#[cfg(not(test))]
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

    // Risk and Performance types
    m.add_class::<WarModeState>()?;
    m.add_class::<RiskEngine>()?;
    m.add_class::<StatsEngine>()?;
    m.add_class::<SizingEngine>()?;
    m.add_class::<MathEngine>()?;
    m.add_class::<MicrostructureEngine>()?;

    // Simulator types
    m.add_class::<SimulatorConfig>()?;
    m.add_function(wrap_pyfunction!(run_simulation_1d, m)?)?;
    m.add_function(wrap_pyfunction!(run_hft_simulation, m)?)?;

    Ok(())
}
