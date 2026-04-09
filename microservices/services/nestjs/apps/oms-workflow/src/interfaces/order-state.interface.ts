import { OrderStatus } from '../constants/order-status.enum';

export interface FillRecord {
  fillId: string;
  price: number;
  quantity: number;
  timestampNs: number;
  venue: string;
}

export interface OrderState {
  orderId: string;
  sessionId: string;
  traceId: string;
  symbol: string;
  status: OrderStatus;
  side: 'BUY' | 'SELL';
  totalQuantity: number;
  filledQuantity: number;
  remainingQuantity: number;
  averagePrice: number;
  fills: FillRecord[];
  createdAt: number;
  updatedAt: number;
  idempotencyKey?: string;
}
