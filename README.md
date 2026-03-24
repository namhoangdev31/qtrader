# QTrader — Institutional-grade Quantitative Trading Framework 🚀📈

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Polars](https://img.shields.io/badge/Polars-Blazing%20Fast-orange.svg)](https://pola.rs/)
[![Rust](https://img.shields.io/badge/Rust-Kernel-black.svg)](https://www.rust-lang.org/)
[![Status](https://img.shields.io/badge/Status-Early%20Alpha-red.svg)]()

QTrader is a high-performance, event-driven algorithmic trading and research framework built for institutional-grade autonomous operations. Designed for **Apple Silicon (M4)** and built with a hybrid Rust/Python architecture, it bridges the gap between deep quantitative research and nanosecond-latency execution.

---

## 🏗️ System Architecture & Engines

QTrader is powered by a set of specialized **Engines** that orchestrate the trading lifecycle. For a deep dive into how these engines interact, see [ENGINES_ARCHITECTURE.md](file:///home/lkct-lee-park/var/www/qtrader/docs/ENGINES_ARCHITECTURE.md).

- **Research & Vectorization**: Native `Polars` integration via `VectorizedEngine` for ultra-fast backtesting.
- **Microstructure Kernel**: Native Rust (`RustTickEngine`) optimized for L2/L3 orderbook simulations.
- **Adaptive Learning**: `MetaLearningEngine` (GMM-based) for real-time market regime detection and dynamic strategy weighting.
- **Recursive Feedback**: `FeedbackEngine` for closed-loop learning from trade executions (fills and slippage).
- **Runtime Risk**: `RuntimeRiskEngine` provides parametric VaR, exposure limits, and automatic drawdown enforcement.

---

## 🎯 Core Capabilities

1. **Advanced Alpha Layer**: Includes `CandleAlphaEngine` with 27 institutional-grade pattern features. Built-in `FeatureValidator` measures IC decay and stability to prevent over-fitting.
2. **Probabilistic Strategy**: Moves beyond binary 0/1 signals. Uses an `EnsembleStrategy` to convert alpha combinations into dynamic, probability-weighted signals.
3. **Institutional Portfolio Allocation**: Implements True Risk Parity using Ledoit-Wolf Shrinkage and Volatility Targeting, treating assets as a correlated matrix.
4. **Smart Execution & OMS**: Unified Order Management System (OMS) with support for Smart Order Routing (SOR), TWAP/VWAP, and Paper/Shadow trading modes.

---

## 🛑 Project Status & Critical Assessment (March 2026)

> [!WARNING]
> **QTrader is currently in EARLY ALPHA and is NOT ready for real-money live trading.**

Based on the [FINAL_PROJECT_EVALUATION.md](file:///home/lkct-lee-park/var/www/qtrader/docs/FINAL_PROJECT_EVALUATION.md), here is the current assessment:

### ✅ Strengths

- **Modular Pipeline**: High degree of separation between Data, Features, Risk, and Execution.
- **Feature Integrity**: Robust validation layer for signal quality (IC Decay monitoring).
- **M4 Optimization**: Leverages Apple Silicon's hardware acceleration for crypto-heavy operations.

### ⚠️ Gaps & Risks

- **State Desync**: Potential mismatch between local OMS and Exchange state during network instability.
- **Transaction Cost Sensitivity**: High regime-flicker can lead to "whipsawing" and fee-burn.
- **Python Latency**: The Global Interpreter Lock (GIL) may introduce jitter in high-frequency event loops compared to the pure Rust kernel.
- **Kill Switch**: Lack of a hardware-level/networking kill switch; system relies on software-level risk checks.

---

## 📂 Project Structure

```text
qtrader/
├── bot/              # Live Trading Runner (Entry point)
├── pipeline/         # Master orchestration (Research -> Deploy -> LiveMonitor)
├── qtrader/          # CORE PYTHON PACKAGE
│   ├── alpha/        # Raw signal generators & AlphaEngine
│   ├── backtest/     # Vectorized & Event-driven Simulators
│   ├── execution/    # SOR, OMS, PaperTradingEngine
│   ├── feedback/     # FeedbackEngine for closed-loop learning
│   ├── ml/           # Regime detection (GMM), MetaLearningEngine
│   ├── risk/         # RuntimeRiskEngine, VaR limits
│   └── strategy/     # Ensemble & Probabilistic decision making
├── rust_core/        # Rust kernel for low-latency calculations
├── docs/             # Architecture, Evaluations, and Engine Documentation
```

---

## 🚀 Quick Start

### 1. Requirements

- Python 3.10+
- Rust toolchain (for native kernel)
- `uv` (fast package manager)
- Docker Desktop (For supplementary infra)

### 2. Environment Setup

```bash
# Clone the repository
git clone https://github.com/hoangnamdev31/qtrader.git
cd qtrader

# Copy the configuration template
cp configs/env.example .env

# Install dependencies and build Rust core
make install
make rust-build
```

### 3. Verify Installation

```bash
python -c "import qtrader; print('QTrader framework initialized successfully!')"
```

---

## 🛡️ Important Disclaimer

Trading financial markets involves high risk. This software is provided for research and educational purposes only. **Always** perform extensive paper trading and risk monitoring before live deployment.

_Built for autonomous quantitative operations. 2026._
