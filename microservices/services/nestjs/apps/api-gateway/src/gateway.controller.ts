import { Body, Controller, Get, Headers, Param, Post } from '@nestjs/common';
import { randomUUID } from 'crypto';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';
import { resolveTraceFromHeaders } from '@common/trace';
import { MetricsPayload } from '@common/types';

import { GrpcClientsService } from './grpc-clients.service';

@Controller('gateway')
export class GatewayController {
  constructor(
    private readonly grpcClients: GrpcClientsService,
    private readonly metrics: MetricsService,
    private readonly logger: JsonLoggerService,
  ) {}

  @Post('sessions/start')
  async startSession(
    @Body() body: { session_id?: string },
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_sessions_start');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    const res = await this.grpcClients.sessionStart(body, trace);
    this.logger.log('gateway.sessions.start', { trace_id: trace.traceId, response: res });
    return res;
  }

  @Post('sessions/halt')
  async haltSession(
    @Body() body: { reason?: string },
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_sessions_halt');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    return this.grpcClients.sessionHalt({ reason: body.reason ?? 'MANUAL_HALT' }, trace);
  }

  @Get('sessions/status')
  async sessionStatus(
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_sessions_status');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    return this.grpcClients.sessionStatus(trace);
  }

  @Post('orders/create')
  async createOrder(
    @Body()
    body: {
      symbol: string;
      action: 'BUY' | 'SELL';
      quantity: number;
      price: number;
      idempotency_key?: string;
    },
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_orders_create');
    const trace = resolveTraceFromHeaders(traceId, sessionId);

    const risk = await this.grpcClients.riskValidate(
      {
        symbol: body.symbol,
        action: body.action,
        quantity: body.quantity,
        price: body.price,
      },
      trace,
    );

    if (!risk.approved) {
      return { status: 'REJECTED', reason: risk.reason, trace_id: trace.traceId };
    }

    return this.grpcClients.omsCreate(
      {
        order_id: randomUUID(),
        session_id: trace.sessionId,
        trace_id: trace.traceId,
        symbol: body.symbol,
        action: body.action,
        quantity: body.quantity,
        idempotency_key: body.idempotency_key,
      },
      trace,
    );
  }

  @Post('orders/:order_id/transition')
  async transitionOrder(
    @Param('order_id') orderId: string,
    @Body() body: { status: string },
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_orders_transition');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    return this.grpcClients.omsTransition({ order_id: orderId, status: body.status }, trace);
  }

  @Get('orders/:order_id')
  async getOrder(
    @Param('order_id') orderId: string,
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_orders_get');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    return this.grpcClients.omsGet({ order_id: orderId }, trace);
  }

  @Get('orders')
  async listOrders(
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_orders_list');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    return this.grpcClients.omsList(trace);
  }

  @Get('reports/session-summary/:session_id')
  async getSessionSummary(
    @Param('session_id') sessionIdParam: string,
    @Headers('x-trace-id') traceId?: string,
    @Headers('x-session-id') sessionId?: string,
  ): Promise<Record<string, unknown>> {
    this.metrics.increment('http_reports_summary');
    const trace = resolveTraceFromHeaders(traceId, sessionId);
    return this.grpcClients.reportSummary({ session_id: sessionIdParam }, trace);
  }

  @Get('health')
  health(): { service: string; status: string; timestamp: string } {
    return { service: 'api-gateway', status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('ready')
  ready(): { service: string; status: string } {
    return { service: 'api-gateway', status: 'ok' };
  }

  @Get('metrics')
  metricsSnapshot(): MetricsPayload {
    return this.metrics.snapshot('api-gateway');
  }
}
