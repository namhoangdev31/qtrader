# QTrader v4 — Autonomous Trading Framework (2026) 🚀📈

QTrader is an institutional-grade, high-performance algorithmic trading and research framework designed for autonomous operations in multi-venue environments. Optimized for **Apple Silicon M4** and built with a hybrid Rust/Python architecture.

---

## 🏗️ Architecture Stack

- **Execution Kernel**: Native Rust (ARM64 Optimized) for nano-second latency L2 orderbook processing.
- **Research Layer**: Python 3.10 (Standardized) using Polars, Apache Arrow, and Scikit-Learn.
- **Data Persistence**: **PostgreSQL / TimescaleDB** for relational metadata and **ArcticDB** for high-performance tick storage.
- **Distributed Compute**: **Ray** for hyperparameter tuning and massive factor calculation.
- **Monitoring & Lifecycle**: **MLflow** for model versioning and tracking autonomous rotations.

---

## 💻 Apple Silicon (M4) Optimization

The system uses a **Hybrid Infrastructure** for peak performance:

- **Native M4 (Mac)**: Rust kernel compilation and local research (via `make rust-build`).
- **Emulated (Docker Rosetta)**: Python application layer (`linux/amd64`) to support complex libraries like `ArcticDB`.
- **Native ARM (Docker)**: Database and observability services (`timescaledb`, `mlflow`).

---

## 🚀 Quick Start

### 1. Requirements

- Docker Desktop (Rosetta 2 enabled)
- Python 3.10+
- Rust toolchain (for native kernel)
- `uv` (fast package manager)

### 2. Configuration

Copy the template and fill in your API keys:

```bash
cp configs/env.example .env
```

### 3. Deployment

```bash
make docker-up
```

_Note: If port 5000 is occupied (e.g., by another MLflow instance or MacOS AirPlay Receiver), please ensure it is free._

---

## 🛠️ Makefile Commands

| Command           | Description                             |
| :---------------- | :-------------------------------------- |
| `make install`    | Install Python dependencies using `uv`  |
| `make rust-build` | Compile the Rust kernel natively for M4 |
| `make docker-up`  | Start the full trading stack in Docker  |
| `make test`       | Run unit and integration tests          |
| `make clean`      | Purge temporary cache and build files   |

---

## 🛡️ Operational Guardrails

- **Flash Crash Protection**: AI-driven safety layer monitoring liquidity drops.
- **Risk Engine**: Hardened OMS with SOR for multi-exchange neutrality.
- **Budget Circuit Breaker**: Real-time cloud cost tracking.

---

## 📊 Data Lake Structure

The data lake is managed via `UniversalDataLake`, supporting:

- Local filesystem (`./data_lake`)
- AWS S3 / S3-Compatible storage
- Google Cloud Storage (GCS)

---

**Developed for QTrader 2026 Autonomous Operations.**
