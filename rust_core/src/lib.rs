use pyo3::prelude::*;

pub mod allocator;
pub mod algo;
pub mod event_store;
pub mod execution;
pub mod matching;
pub mod math;
pub mod microstructure;
pub mod models;
pub mod oms;
pub mod oms_engine;
pub mod portfolio;
pub mod persistence;
pub mod risk;
pub mod router;
pub mod simulator;
pub mod sizing;
pub mod stats;

#[cfg(test)]
mod tests;

/// A Python module implemented in Rust.
#[cfg(not(test))]
#[pymodule]
fn qtrader_core(_py: Python, m: &PyModule) -> PyResult<()> {
    use crate::allocator::{AllocationReport, CapitalAllocator};
    use crate::algo::TwapAlgo;
    use crate::event_store::EventStore;
    use crate::execution::ExecutionEngine;
    use crate::matching::MatchingEngine;
    use crate::math::MathEngine;
    use crate::microstructure::MicrostructureEngine;
    use crate::models::{LatencyModel, SlippageModel};
    use crate::oms::{Account, Order, OrderStatus, OrderType, Position, Side};
    use crate::oms_engine::{OrderFSM, UnifiedOMS};
    use crate::portfolio::{LedgerEngine, NAVReport, PortfolioEngine, PortfolioLedgerEntry};
    use crate::risk::{RiskEngine, WarModeState};
    use crate::router::{RoutingMode, SmartOrderRouter};
    use crate::simulator::{run_hft_simulation, run_simulation_1d, SimulatorConfig};
    use crate::sizing::SizingEngine;
    use crate::stats::StatsEngine;

    // OMS types
    m.add_class::<Side>()?;
    m.add_class::<OrderType>()?;
    m.add_class::<OrderStatus>()?;
    m.add_class::<Order>()?;
    m.add_class::<Position>()?;
    m.add_class::<Account>()?;
    m.add_class::<OrderFSM>()?;
    m.add_class::<UnifiedOMS>()?;
    m.add_class::<EventStore>()?;

    // Execution types
    m.add_class::<MatchingEngine>()?;
    m.add_class::<TwapAlgo>()?;
    m.add_class::<ExecutionEngine>()?;
    m.add_class::<SmartOrderRouter>()?;
    m.add_class::<RoutingMode>()?;
    m.add_class::<SlippageModel>()?;
    m.add_class::<LatencyModel>()?;

    // Risk and Performance types
    m.add_class::<WarModeState>()?;
    m.add_class::<RiskEngine>()?;
    m.add_class::<StatsEngine>()?;
    m.add_class::<SizingEngine>()?;
    m.add_class::<MathEngine>()?;
    m.add_class::<MicrostructureEngine>()?;

    // Portfolio types
    m.add_class::<PortfolioEngine>()?;
    m.add_class::<NAVReport>()?;
    m.add_class::<LedgerEngine>()?;
    m.add_class::<PortfolioLedgerEntry>()?;
    m.add_class::<CapitalAllocator>()?;
    m.add_class::<AllocationReport>()?;

    // Simulator types
    m.add_class::<SimulatorConfig>()?;
    m.add_function(wrap_pyfunction!(run_simulation_1d, m)?)?;
    m.add_function(wrap_pyfunction!(run_hft_simulation, m)?)?;

    Ok(())
}
