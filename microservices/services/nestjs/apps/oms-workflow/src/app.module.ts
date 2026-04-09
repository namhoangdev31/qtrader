import { Module } from '@nestjs/common';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';

import { OmsController } from './oms.controller';
import { OmsService } from './oms.service';

@Module({
  controllers: [OmsController],
  providers: [OmsService, MetricsService, JsonLoggerService],
})
export class AppModule {}
