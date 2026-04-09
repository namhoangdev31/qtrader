import { BadRequestException, Injectable, Logger } from '@nestjs/common';

const INSTITUTIONAL_NOTIONAL_LIMIT_USD = 1_000_000;

@Injectable()
export class RiskPolicyService {
  private readonly logger = new Logger(RiskPolicyService.name);

  async validateOrder(order: { symbol: string; quantity: number; price?: number }): Promise<void> {
    const notional = (order.price ?? 0) * order.quantity;
    this.logger.log(`[RISK-POLICY] Pre-checking order for ${order.symbol} | Notional=${notional}`);

    if (notional > INSTITUTIONAL_NOTIONAL_LIMIT_USD) {
      throw new BadRequestException('EXCEEDS_INSTITUTIONAL_HARD_LIMIT');
    }
  }
}
