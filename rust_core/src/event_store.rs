use pyo3::prelude::*;
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SystemEvent {
    pub source: String,
    pub trace_id: String,
    pub action: String,
    pub symbol: Option<String>,
    pub order_id: Option<u64>,
    pub timestamp: String,
    pub metadata: Option<serde_json::Value>,
}

#[pyclass]
pub struct EventStore {
    #[pyo3(get)]
    pub log_path: String,
}

#[pymethods]
impl EventStore {
    #[new]
    pub fn new(log_path: String) -> Self {
        EventStore { log_path }
    }

    pub fn record_event(&self, json_payload: String) -> PyResult<()> {
        use crate::persistence::{PersistenceWorker, PersistenceTask};
        
        // Non-blocking submission to background worker
        PersistenceWorker::global().submit(PersistenceTask::RecordEvent(json_payload));

        Ok(())
    }
}
