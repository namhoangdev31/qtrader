import { Body, Controller, Get, Param, Post } from '@nestjs/common';

import { OrderStatus } from './constants/order-status.enum';
import { OmsWorkflow } from './oms.workflow';

@Controller('oms')
export class OmsController {
  constructor(private readonly omsWorkflow: OmsWorkflow) {}

  @Get('orders')
  list(): ReturnType<OmsWorkflow['listOrders']> {
    return this.omsWorkflow.listOrders();
  }

  @Get('orders/:orderId')
  getOne(@Param('orderId') orderId: string): ReturnType<OmsWorkflow['getOrder']> {
    return this.omsWorkflow.getOrder(orderId);
  }

  @Post('orders/:orderId/transition')
  async transition(
    @Param('orderId') orderId: string,
    @Body() body: { status: OrderStatus },
  ): Promise<{ ok: boolean }> {
    await this.omsWorkflow.handleTransition(orderId, body.status, {});
    return { ok: true };
  }
}
