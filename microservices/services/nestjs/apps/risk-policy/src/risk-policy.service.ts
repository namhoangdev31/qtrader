import { Injectable } from '@nestjs/common';

const INSTITUTIONAL_NOTIONAL_LIMIT_USD = 1_000_000;

@Injectable()
export class RiskPolicyService {
  validateOrder(input: {
    symbol: string;
    action: string;
    quantity: number;
    price: number;
  }): { approved: boolean; reason: string } {
    const notional = input.quantity * input.price;

    if (notional > INSTITUTIONAL_NOTIONAL_LIMIT_USD) {
      return { approved: false, reason: 'EXCEEDS_INSTITUTIONAL_HARD_LIMIT' };
    }

    if (input.quantity <= 0) {
      return { approved: false, reason: 'INVALID_QUANTITY' };
    }

    if (input.action !== 'BUY' && input.action !== 'SELL') {
      return { approved: false, reason: 'INVALID_ACTION' };
    }

    return { approved: true, reason: 'APPROVED' };
  }
}
