# QTrader Microservices

Hybrid microservices scaffold for QTrader:

- Control Plane: NestJS (`services/nestjs`)
- Compute Plane: Python (`services/python`)
- Contracts: protobuf (`proto`)

## Service map

- `nestjs-control-plane`:
  - session lifecycle
  - order command + OMS workflow
  - risk policy pre-check
  - reporting query APIs
- `python-execution-core`:
  - execution stub (Rust bridge integration point)
- `python-alpha-feature`:
  - Polars-based feature computation

## Run (Docker)

```bash
cd microservices
docker compose -f infra/docker-compose.yml up --build
```

## Quick test

```bash
curl http://localhost:3100/health
curl -X POST http://localhost:3100/session/start
curl -X POST http://localhost:3100/orders \
  -H 'content-type: application/json' \
  -d '{"symbol":"BTC-USD","action":"BUY","quantity":0.1,"price":65000,"idempotencyKey":"demo-1"}'
```
