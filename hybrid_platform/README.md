# QTrader Hybrid Microservices Scaffold (NestJS + Python + Rust)

Scaffold nay phuc vu migration 80% control-plane sang NestJS, giu lai compute-plane cho Polars/ML/Rust.

## Architecture (high-level)

- `nestjs-api-gateway`: Auth/RBAC/MFA, HTTP/WebSocket, edge rate-limit.
- `nestjs-session-control`: start/stop session, lifecycle, health orchestration.
- `nestjs-oms-workflow`: order workflow, idempotency, retry policy, audit event.
- `python-alpha-ml`: feature engineering (Polars) + model inference.
- `python-execution-core`: execution/risk compute bridge to Rust core.

## Quick start

```bash
cd scratch/hybrid_platform

docker compose -f infra/docker-compose.hybrid.yml up --build
```

API test:

```bash
curl http://localhost:3000/health
curl -X POST http://localhost:3000/api/v1/session/start
curl -X POST http://localhost:3000/api/v1/orders \
  -H 'content-type: application/json' \
  -d '{"symbol":"BTC-USD","side":"BUY","qty":0.1,"idempotency_key":"demo-1"}'
```
