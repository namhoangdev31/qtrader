import { Body, Controller, Headers, Logger, Post } from '@nestjs/common';
import { randomUUID } from 'crypto';

import { OrderStatus } from '../oms-workflow/constants/order-status.enum';
import { OmsWorkflow } from '../oms-workflow/oms.workflow';
import { RiskPolicyService } from '../risk-policy/risk.policy';

interface OrderCommandRequest {
  symbol: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  price?: number;
  idempotencyKey?: string;
}

@Controller('orders')
export class OrderController {
  private readonly logger = new Logger(OrderController.name);

  constructor(
    private readonly riskPolicyService: RiskPolicyService,
    private readonly omsWorkflow: OmsWorkflow,
  ) {}

  @Post()
  async createOrder(
    @Body() orderDto: OrderCommandRequest,
    @Headers('x-trace-id') traceIdHeader?: string,
    @Headers('x-session-id') sessionIdHeader?: string,
  ): Promise<{ orderId: string; traceId: string; status: string }> {
    const orderId = randomUUID();
    const traceId = traceIdHeader ?? randomUUID();
    const sessionId = sessionIdHeader ?? 'GLOBAL_IDLE';

    await this.riskPolicyService.validateOrder({
      symbol: orderDto.symbol,
      quantity: orderDto.quantity,
      price: orderDto.price,
    });

    const state = this.omsWorkflow.createOrder({
      orderId,
      sessionId,
      traceId,
      symbol: orderDto.symbol,
      side: orderDto.action,
      quantity: orderDto.quantity,
      idempotencyKey: orderDto.idempotencyKey,
    });

    await this.omsWorkflow.handleTransition(state.orderId, OrderStatus.ROUTED, {});

    this.logger.log(`[ORDER-COMMAND] Order ${orderId} routed | Trace: ${traceId}`);

    return {
      orderId,
      traceId,
      status: OrderStatus.ROUTED,
    };
  }
}
