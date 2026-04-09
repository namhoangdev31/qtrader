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
      package: 'qtrader.v1.risk',
      protoPath: join(__dirname, '../../../proto/v1/risk.proto'),
      url: process.env.RISK_POLICY_GRPC_URL ?? '0.0.0.0:50063',
    },
  });

  await app.startAllMicroservices();
  await app.listen(Number(process.env.RISK_POLICY_HTTP_PORT ?? 3103));
}

void bootstrap();
