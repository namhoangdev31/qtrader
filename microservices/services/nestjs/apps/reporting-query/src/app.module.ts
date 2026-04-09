import { Module } from '@nestjs/common';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';

import { ReportingController } from './reporting.controller';
import { ReportingService } from './reporting.service';

@Module({
  controllers: [ReportingController],
  providers: [ReportingService, MetricsService, JsonLoggerService],
})
export class AppModule {}
