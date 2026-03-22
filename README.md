# QTrader — Institutional-grade Quantitative Trading Framework 🚀📈

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Polars](https://img.shields.io/badge/Polars-Blazing%20Fast-orange.svg)](https://pola.rs/)
[![Rust](https://img.shields.io/badge/Rust-Kernel-black.svg)](https://www.rust-lang.org/)
[![Status](https://img.shields.io/badge/Status-Active%20Development-success.svg)]()

QTrader is a high-performance, event-driven algorithmic trading and research framework built for institutional-grade autonomous operations. Designed for **Apple Silicon (M4)** and built with a hybrid Rust/Python architecture, it bridges the gap between deep quantitative research and nanosecond-latency execution.

---

## 🏗️ Architecture Stack

- **Data & Features**: Built purely on `Polars` for fully vectorized, zero-loop dataframe operations.
- **Execution Kernel**: Native Rust (`qtrader_core`) optimized for L2 microstructure extraction.
- **Event-Driven Orchestrator**: `asyncio` based EventBus handling MarketData $\rightarrow$ Features $\rightarrow$ Alpha $\rightarrow$ Signals $\rightarrow$ Orders $\rightarrow$ Risk.
- **Machine Learning**: Walk-forward optimization via `CatBoost` and Online Market Regime Detection via `Gaussian Mixture Models (GMM)`.

---

## 🎯 Core Capabilities

1. **Alpha Engine**: Ships with 27 institutional-grade candlestick and price-action features. Includes a `FeatureValidator` that actively measures Information Coefficient (IC) decay and zeros out bad signals.
2. **Strategy Engine**: Uses `ProbabilisticStrategy` and `EnsembleStrategy` to convert alpha combinations into dynamic, probability-weighted signals instead of rigid `0/1` binary outputs.
3. **Portfolio Allocation**: Implements True Risk Parity using Ledoit-Wolf Shrinkage and Volatility Targeting, treating assets as a correlated matrix rather than isolated bets.
4. **Runtime Risk Engine**: Real-time VaR (Value at Risk), Drawdown tracking, and Exposure computation tied directly to OMS data.
5. **Smart Execution**: Includes an L2 Simulator for backtesting with queue priority, partial fills, and a Smart Order Router (SOR) for execution.

---

## 📂 Project Structure

Following a massive refactoring, QTrader enforces a strict separation of concerns within a single Python package:

```text
qtrader/
├── bot/              # Live Trading Runner (Entry point)
├── pipeline/         # Master orchestration (Research -> Deploy -> LiveMonitor)
├── qtrader/          # CORE PYTHON PACKAGE
│   ├── alpha/        # Raw signal generators
│   ├── api/          # Exchange wrappers (Binance, Coinbase)
│   ├── backtest/     # Vectorized Engine & Event-driven Simulators
│   ├── execution/    # Smart Order Routing (SOR), OMS, TWAP/VWAP Algos
│   ├── ml/           # Regime detection, Walk-forward ML
│   ├── portfolio/    # Allocation (HRP, Risk Parity)
│   ├── risk/         # Runtime Risk, Drawdown enforcement
│   └── strategy/     # Probabilistic/Ensemble decision making
├── rust_core/        # Rust kernel for low-latency calculations
├── tests/            # Unit & Integration tests
└── docs/             # Comprehensive evaluation & architecture reports
```

---

## 💻 Apple Silicon (M4) Optimization

The system uses a **Hybrid Infrastructure** for peak performance:

- **Native M4 (Mac)**: Rust kernel compilation and local research (via `make rust-build`).
- **Python Backend**: Strictly targetting Python 3.10+ using `uv` for lightning-fast capability.

---

## 🚀 Quick Start

### 1. Requirements

- Python 3.10+
- Rust toolchain (for native kernel)
- `uv` (fast package manager)
- Docker Desktop (If running full DB stack)

### 2. Environment Setup

```bash
# Clone the repository
git clone https://github.com/hoangnamdev31/qtrader.git
cd qtrader

# Copy the configuration template
cp configs/env.example .env

# Install dependencies blazingly fast with uv
make install

# Compile the Rust core (Required for microstructure features)
make rust-build
```

### 3. Verify Installation

```bash
python -c "import qtrader; print('QTrader framework initialized successfully!')"
```

---

## 🛠️ Makefile Commands

| Command           | Description                             |
| :---------------- | :-------------------------------------- |
| `make install`    | Install Python dependencies using `uv`  |
| `make rust-build` | Compile the Rust kernel natively for M4 |
| `make test`       | Run all Pytest suites                   |
| `make docker-up`  | Start the supplementary infra in Docker |
| `make clean`      | Purge temporary cache and build files   |

---

## 🛡️ Important Disclaimer & Financial Risk

**CRITICAL WARNING:** QTrader is currently evaluated as **Not Ready for Real-Money Live Trading**.
While the architectural foundation is excellent, trading real capital requires hard-coded kill switches at the network level, advanced Shadow Mode (Paper Trading) verification, and strict turnover constraints to prevent transaction cost ruin (whipsawing).

**ALWAYS** run extensive paper trading and drift monitoring before attaching live API keys. This software is provided for research and educational purposes only.

---

_Built for autonomous quantitative operations. 2026._
