import { OrderStatus } from './constants/order-status.enum';
import { isValidTransition } from './transition';

describe('OMS transition matrix', () => {
  it('accepts valid transition ROUTED -> ACK', () => {
    expect(isValidTransition(OrderStatus.ROUTED, OrderStatus.ACKNOWLEDGED)).toBe(true);
  });

  it('rejects invalid transition FILLED -> ACK', () => {
    expect(isValidTransition(OrderStatus.FILLED, OrderStatus.ACKNOWLEDGED)).toBe(false);
  });

  it('accepts PARTIAL -> FILLED', () => {
    expect(isValidTransition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)).toBe(true);
  });
});
