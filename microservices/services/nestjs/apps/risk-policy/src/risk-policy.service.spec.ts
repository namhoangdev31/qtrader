import { RiskPolicyService } from './risk-policy.service';

describe('RiskPolicyService', () => {
  const svc = new RiskPolicyService();

  it('rejects notional above hard limit', () => {
    const result = svc.validateOrder({
      symbol: 'BTC-USD',
      action: 'BUY',
      quantity: 100,
      price: 20000,
    });
    expect(result.approved).toBe(false);
    expect(result.reason).toBe('EXCEEDS_INSTITUTIONAL_HARD_LIMIT');
  });

  it('approves valid order', () => {
    const result = svc.validateOrder({
      symbol: 'BTC-USD',
      action: 'SELL',
      quantity: 0.5,
      price: 60000,
    });
    expect(result.approved).toBe(true);
  });
});
