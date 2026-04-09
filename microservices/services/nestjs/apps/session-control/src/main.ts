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
      package: 'qtrader.v1.session',
      protoPath: join(__dirname, '../../../proto/v1/session.proto'),
      url: process.env.SESSION_CONTROL_GRPC_URL ?? '0.0.0.0:50061',
    },
  });

  await app.startAllMicroservices();
  await app.listen(Number(process.env.SESSION_CONTROL_HTTP_PORT ?? 3101));
}

void bootstrap();
