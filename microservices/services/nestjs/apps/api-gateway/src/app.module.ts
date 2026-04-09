import { Module } from '@nestjs/common';

import { JsonLoggerService } from '@common/json-logger.service';
import { MetricsService } from '@common/metrics.service';
import { ServiceRegistryService } from '@common/service-registry.service';

import { GatewayController } from './gateway.controller';
import { GrpcClientsService } from './grpc-clients.service';

@Module({
  controllers: [GatewayController],
  providers: [GrpcClientsService, ServiceRegistryService, MetricsService, JsonLoggerService],
})
export class AppModule {}
