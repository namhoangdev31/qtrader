import { Body, Controller, Get } from '@nestjs/common';
import { GrpcMethod } from '@nestjs/microservices';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';
import { MetricsPayload } from '@common/types';

import { ReportingService } from './reporting.service';

@Controller()
export class ReportingController {
  constructor(
    private readonly reportingService: ReportingService,
    private readonly metrics: MetricsService,
    private readonly logger: JsonLoggerService,
  ) {}

  @GrpcMethod('ReportingService', 'GetSessionSummary')
  getSessionSummary(@Body() body: { session_id: string }): {
    session_id: string;
    sharpe: number;
    win_rate: number;
    trades: number;
  } {
    this.metrics.increment('grpc_get_session_summary');
    const sessionId = body?.session_id ?? 'UNKNOWN_SESSION';
    const result = this.reportingService.getSessionSummary(sessionId);
    this.logger.log('reporting.session_summary', result);
    return result;
  }

  @Get('health')
  health(): { service: string; status: string; timestamp: string } {
    return { service: 'reporting-query', status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('ready')
  ready(): { service: string; status: string } {
    return { service: 'reporting-query', status: 'ok' };
  }

  @Get('metrics')
  metricsSnapshot(): MetricsPayload {
    return this.metrics.snapshot('reporting-query');
  }
}
