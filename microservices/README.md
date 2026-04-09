# QTrader Microservices

NestJS control-plane is now deployed as a **monorepo with 5 independent services**:

- `api-gateway` (HTTP entrypoint)
- `session-control` (gRPC + health)
- `oms-workflow` (gRPC + Redis state/idempotency)
- `risk-policy` (gRPC pre-trade validation)
- `reporting-query` (gRPC reporting)

Python compute-plane services remain available for hybrid rollout.

## Architecture

See [docs/architecture.mmd](docs/architecture.mmd).

## Run

```bash
cd microservices
docker compose -f infra/docker-compose.yml up --build
```

## Gateway API (v1)

All user-facing HTTP routes are namespaced under `/gateway/*`.

### Sessions

```bash
curl -X POST http://localhost:3100/gateway/sessions/start
curl http://localhost:3100/gateway/sessions/status
curl -X POST http://localhost:3100/gateway/sessions/halt \
  -H 'content-type: application/json' \
  -d '{"reason":"MANUAL"}'
```

### Orders

```bash
curl -X POST http://localhost:3100/gateway/orders/create \
  -H 'content-type: application/json' \
  -d '{"symbol":"BTC-USD","action":"BUY","quantity":0.1,"price":65000,"idempotency_key":"demo-1"}'

curl http://localhost:3100/gateway/orders
curl http://localhost:3100/gateway/orders/<order_id>
curl -X POST http://localhost:3100/gateway/orders/<order_id>/transition \
  -H 'content-type: application/json' \
  -d '{"status":"ACK"}'
```

### Reporting

```bash
curl http://localhost:3100/gateway/reports/session-summary/sess_123
```

## Required headers

- `x-trace-id`: optional (auto-generated if missing)
- `x-session-id`: optional (`GLOBAL_IDLE` default)

## Proto tooling

```bash
./common/scripts/generate_protos.sh generate
./common/scripts/generate_protos.sh check
```
