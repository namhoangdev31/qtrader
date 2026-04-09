import { Body, Controller, Get } from '@nestjs/common';
import { GrpcMethod } from '@nestjs/microservices';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';
import { MetricsPayload } from '@common/types';

import { RiskPolicyService } from './risk-policy.service';

@Controller()
export class RiskPolicyController {
  constructor(
    private readonly riskPolicyService: RiskPolicyService,
    private readonly metrics: MetricsService,
    private readonly logger: JsonLoggerService,
  ) {}

  @GrpcMethod('RiskPolicyService', 'ValidateOrder')
  validateOrder(
    @Body() body: { symbol: string; action: string; quantity: number; price: number },
  ): { approved: boolean; reason: string } {
    this.metrics.increment('grpc_validate_order');
    const result = this.riskPolicyService.validateOrder(body);
    this.logger.log('risk.validate_order', { ...body, ...result });
    return result;
  }

  @Get('health')
  health(): { service: string; status: string; timestamp: string } {
    return { service: 'risk-policy', status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('ready')
  ready(): { service: string; status: string } {
    return { service: 'risk-policy', status: 'ok' };
  }

  @Get('metrics')
  metricsSnapshot(): MetricsPayload {
    return this.metrics.snapshot('risk-policy');
  }
}
