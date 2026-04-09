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
      package: 'qtrader.v1.oms',
      protoPath: join(__dirname, '../../../proto/v1/oms.proto'),
      url: process.env.OMS_WORKFLOW_GRPC_URL ?? '0.0.0.0:50062',
    },
  });

  await app.startAllMicroservices();
  await app.listen(Number(process.env.OMS_WORKFLOW_HTTP_PORT ?? 3102));
}

void bootstrap();
