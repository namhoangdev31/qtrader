import { OrderStatus } from './constants/order-status.enum';

export const ORDER_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  [OrderStatus.PENDING]: [OrderStatus.ROUTED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
  [OrderStatus.ROUTED]: [OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
  [OrderStatus.ACKNOWLEDGED]: [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED],
  [OrderStatus.PARTIALLY_FILLED]: [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED],
  [OrderStatus.FILLED]: [],
  [OrderStatus.CANCELLED]: [],
  [OrderStatus.REJECTED]: [],
  [OrderStatus.EXPIRED]: [],
};

export function isValidTransition(from: OrderStatus, to: OrderStatus): boolean {
  return ORDER_TRANSITIONS[from].includes(to);
}
