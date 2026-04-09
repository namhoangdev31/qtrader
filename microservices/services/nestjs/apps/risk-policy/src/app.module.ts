import { Module } from '@nestjs/common';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';

import { RiskPolicyController } from './risk-policy.controller';
import { RiskPolicyService } from './risk-policy.service';

@Module({
  controllers: [RiskPolicyController],
  providers: [RiskPolicyService, MetricsService, JsonLoggerService],
})
export class AppModule {}
