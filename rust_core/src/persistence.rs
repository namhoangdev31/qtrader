use crossbeam_channel::{unbounded, Sender};
use duckdb::{params, Connection};
use once_cell::sync::Lazy;
use std::sync::Arc;
use std::thread;
use std::time::Duration;
use chrono::Utc;

pub enum PersistenceTask {
    RecordEvent(String), // JSON payload
    RecordTransaction {
        tx_id: String,
        description: String,
        asset: String,
        amount: f64,
        entry_type: String,
    },
}

pub struct PersistenceWorker {
    sender: Sender<PersistenceTask>,
}

static WORKER: Lazy<Arc<PersistenceWorker>> = Lazy::new(|| {
    let (tx, rx) = unbounded::<PersistenceTask>();

    thread::spawn(move || {
        let conn = Connection::open("data/qtrader_warehouse.db").expect("Failed to open DuckDB");

        // Initialize tables
        conn.execute(
            "CREATE TABLE IF NOT EXISTS events (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                payload JSON
            )",
            [],
        )
        .expect("Failed to create events table");

        conn.execute(
            "CREATE TABLE IF NOT EXISTS ledger (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tx_id TEXT,
                asset TEXT,
                amount DOUBLE,
                entry_type TEXT,
                description TEXT
            )",
            [],
        )
        .expect("Failed to create ledger table");

        let mut batch = Vec::new();
        let batch_timeout = Duration::from_millis(100);

        loop {
            // Collect batch with timeout
            match rx.recv_timeout(batch_timeout) {
                Ok(task) => {
                    batch.push(task);
                    if batch.len() >= 1000 {
                        flush_batch(&conn, &mut batch);
                    }
                }
                Err(_) => {
                    if !batch.is_empty() {
                        flush_batch(&conn, &mut batch);
                    }
                }
            }
        }
    });

    Arc::new(PersistenceWorker { sender: tx })
});

fn flush_batch(conn: &Connection, batch: &mut Vec<PersistenceTask>) {
    for task in batch.drain(..) {
        match task {
            PersistenceTask::RecordEvent(json) => {
                let _ = conn.execute("INSERT INTO events (payload) VALUES (?)", params![json]);
            }
            PersistenceTask::RecordTransaction {
                tx_id,
                description,
                asset,
                amount,
                entry_type,
            } => {
                let _ = conn.execute(
                    "INSERT INTO ledger (tx_id, asset, amount, entry_type, description) VALUES (?, ?, ?, ?, ?)",
                    params![tx_id, asset, amount, entry_type, description],
                );
            }
        }
    }
}

impl PersistenceWorker {
    pub fn global() -> Arc<Self> {
        WORKER.clone()
    }

    pub fn submit(&self, task: PersistenceTask) {
        let _ = self.sender.send(task);
    }
}
