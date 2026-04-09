import { Body, Controller, Get } from '@nestjs/common';
import { GrpcMethod } from '@nestjs/microservices';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';
import { MetricsPayload } from '@common/types';

import { OrderStatus } from './constants/order-status.enum';
import { OmsService } from './oms.service';

@Controller()
export class OmsController {
  constructor(
    private readonly omsService: OmsService,
    private readonly metrics: MetricsService,
    private readonly logger: JsonLoggerService,
  ) {}

  @GrpcMethod('OmsService', 'CreateOrder')
  async createOrder(
    @Body()
    body: {
      order_id: string;
      session_id: string;
      trace_id: string;
      symbol: string;
      action: 'BUY' | 'SELL';
      quantity: number;
      idempotency_key?: string;
    },
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('grpc_create_order');
    const state = await this.omsService.createOrder({
      orderId: body.order_id,
      sessionId: body.session_id,
      traceId: body.trace_id,
      symbol: body.symbol,
      side: body.action,
      quantity: body.quantity,
      idempotencyKey: body.idempotency_key,
    });
    this.logger.log('oms.create_order', { order_id: body.order_id, status: state.status });
    return this.toOrderReply(state, '');
  }

  @GrpcMethod('OmsService', 'TransitionOrder')
  async transitionOrder(@Body() body: { order_id: string; status: string }): Promise<Record<string, unknown>> {
    this.metrics.increment('grpc_transition_order');
    const state = await this.omsService.transitionOrder(body.order_id, body.status as OrderStatus);
    return this.toOrderReply(state, '');
  }

  @GrpcMethod('OmsService', 'GetOrder')
  async getOrder(@Body() body: { order_id: string }): Promise<Record<string, unknown>> {
    this.metrics.increment('grpc_get_order');
    const state = await this.omsService.getOrder(body.order_id);
    if (!state) {
      return this.toOrderReply(null, 'ORDER_NOT_FOUND');
    }
    return this.toOrderReply(state, '');
  }

  @GrpcMethod('OmsService', 'ListOrders')
  async listOrders(): Promise<{ orders: Record<string, unknown>[] }> {
    this.metrics.increment('grpc_list_orders');
    const rows = await this.omsService.listOrders();
    return { orders: rows.map((row) => this.toOrderReply(row, '')) };
  }

  @GrpcMethod('OmsService', 'HandleFill')
  async handleFill(
    @Body()
    body: {
      order_id: string;
      fill_id: string;
      price: number;
      quantity: number;
      timestamp_ns: number;
      venue: string;
    },
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('grpc_handle_fill');
    const state = await this.omsService.handleFill(body.order_id, {
      fillId: body.fill_id,
      price: body.price,
      quantity: body.quantity,
      timestampNs: body.timestamp_ns,
      venue: body.venue,
    });
    return this.toOrderReply(state, '');
  }

  @Get('health')
  health(): { service: string; status: string; timestamp: string } {
    return { service: 'oms-workflow', status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('ready')
  ready(): { service: string; status: string } {
    return { service: 'oms-workflow', status: 'ok' };
  }

  @Get('metrics')
  metricsSnapshot(): MetricsPayload {
    return this.metrics.snapshot('oms-workflow');
  }

  private toOrderReply(state: {
    orderId: string;
    sessionId: string;
    traceId: string;
    symbol: string;
    status: string;
    side: string;
    totalQuantity: number;
    filledQuantity: number;
    remainingQuantity: number;
  } | null, reason: string): Record<string, unknown> {
    if (!state) {
      return {
        order_id: '',
        session_id: '',
        trace_id: '',
        symbol: '',
        status: 'UNKNOWN',
        action: '',
        total_quantity: 0,
        filled_quantity: 0,
        remaining_quantity: 0,
        reason,
      };
    }

    return {
      order_id: state.orderId,
      session_id: state.sessionId,
      trace_id: state.traceId,
      symbol: state.symbol,
      status: state.status,
      action: state.side,
      total_quantity: state.totalQuantity,
      filled_quantity: state.filledQuantity,
      remaining_quantity: state.remainingQuantity,
      reason,
    };
  }
}
