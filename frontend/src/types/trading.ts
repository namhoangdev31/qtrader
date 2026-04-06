export interface IngestionTrace {
  price: number;
  volatility: number;
  spread_bps: number;
  is_live: boolean;
  timestamp: string;
}

export interface AlphaTrace {
  model_name: string;
  action: string;
  confidence: number;
  indicators: Record<string, number>;
  forecast?: number[];
  reasoning?: string;
}

export interface RiskTrace {
  initial_stop_loss: number;
  initial_take_profit: number;
  adjusted_stop_loss: number;
  adjusted_take_profit: number;
  position_size_pct: number;
  notional_usd: number;
  risk_score: number;
}

export interface ExecutionTrace {
  order_id: string;
  fill_price: number;
  slippage_bps: number;
  fee_usd: number;
  status: string;
}

export interface PipelineTrace {
  ingestion?: IngestionTrace;
  alpha?: AlphaTrace;
  risk?: RiskTrace;
  execution?: ExecutionTrace;
}

export interface SimSnapshot {
  equity: number;
  cash: number;
  realized_pnl: number;
  total_commissions: number;
  total_gross_pnl: number;
  current_price: number;
  thinking_history: any[];
  live_trace?: PipelineTrace;
  open_positions: any[];
  trade_history: any[];
  adaptive: {
    stop_loss_pct: number;
    take_profit_pct: number;
    win_rate: number;
    total_trades: number;
    expected_value: number;
    max_drawdown_pct: number;
    total_wins: number;
    total_losses: number;
  };
  peak_equity: number;
  position_value: number;
}
