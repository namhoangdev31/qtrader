use pyo3::prelude::*;

pub mod oms;
pub mod matching;
pub mod risk;
pub mod algo;
pub mod simulator;

use crate::oms::{Order, Side, OrderType, OrderStatus};
use crate::simulator::{SimulatorConfig, run_simulation_1d};

/// A Python module implemented in Rust.
#[pymodule]
fn qtrader_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<Side>()?;
    m.add_class::<OrderType>()?;
    m.add_class::<OrderStatus>()?;
    m.add_class::<Order>()?;
    m.add_class::<SimulatorConfig>()?;
    
    m.add_function(wrap_pyfunction!(run_simulation_1d, m)?)?;

    Ok(())
}
