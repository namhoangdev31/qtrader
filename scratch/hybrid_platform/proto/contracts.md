# Canonical Event Contracts (first draft)

## OrderCommand

- order_id: string
- symbol: string
- side: BUY | SELL
- qty: number
- price?: number
- order_type: MARKET | LIMIT
- session_id: string
- idempotency_key: string
- trace_id: string

## SignalEvent

- symbol: string
- signal_type: BUY | SELL | HOLD
- strength: number
- confidence: number
- session_id: string
- trace_id: string

## RiskEvent

- symbol: string
- risk_type: DRAWDOWN | VAR | EXPOSURE | POLICY
- action: BLOCK_TRADING | REDUCE_POSITIONS | ALERT
- value: number
- threshold: number
- metadata: object
- trace_id: string

## FillEvent

- order_id: string
- symbol: string
- side: BUY | SELL
- qty: number
- price: number
- fee: number
- venue: string
- session_id: string
- trace_id: string
