import { Body, Controller, Get } from '@nestjs/common';
import { GrpcMethod } from '@nestjs/microservices';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';
import { MetricsPayload } from '@common/types';

import { SessionService } from './session.service';

@Controller()
export class SessionController {
  constructor(
    private readonly sessionService: SessionService,
    private readonly metrics: MetricsService,
    private readonly logger: JsonLoggerService,
  ) {}

  @GrpcMethod('SessionService', 'StartSession')
  startSession(@Body() body: { session_id?: string }): { session_id: string; status: string } {
    this.metrics.increment('grpc_start_session');
    const result = this.sessionService.startSession(body?.session_id);
    this.logger.log('session.start', result);
    return result;
  }

  @GrpcMethod('SessionService', 'HaltSession')
  haltSession(@Body() body: { reason?: string }): { session_id: string; status: string } {
    this.metrics.increment('grpc_halt_session');
    const result = this.sessionService.haltSession(body?.reason ?? 'MANUAL_HALT');
    this.logger.log('session.halt', result);
    return result;
  }

  @GrpcMethod('SessionService', 'GetStatus')
  getStatusGrpc(): { session_id: string; status: string } {
    this.metrics.increment('grpc_get_status');
    return this.sessionService.getStatus();
  }

  @Get('health')
  health(): { service: string; status: string; timestamp: string } {
    return { service: 'session-control', status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('ready')
  ready(): { service: string; status: string } {
    return { service: 'session-control', status: 'ok' };
  }

  @Get('metrics')
  metricsSnapshot(): MetricsPayload {
    return this.metrics.snapshot('session-control');
  }
}
