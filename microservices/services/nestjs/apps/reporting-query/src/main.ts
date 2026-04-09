import 'reflect-metadata';

import { join } from 'path';

import { NestFactory } from '@nestjs/core';
import { MicroserviceOptions, Transport } from '@nestjs/microservices';

import { AppModule } from './app.module';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create(AppModule);

  app.connectMicroservice<MicroserviceOptions>({
    transport: Transport.GRPC,
    options: {
      package: 'qtrader.v1.reporting',
      protoPath: join(__dirname, '../../../proto/v1/reporting.proto'),
      url: process.env.REPORTING_QUERY_GRPC_URL ?? '0.0.0.0:50064',
    },
  });

  await app.startAllMicroservices();
  await app.listen(Number(process.env.REPORTING_QUERY_HTTP_PORT ?? 3104));
}

void bootstrap();
