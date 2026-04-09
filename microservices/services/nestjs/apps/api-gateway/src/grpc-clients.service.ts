import { Injectable, OnModuleDestroy } from '@nestjs/common';
import { credentials, loadPackageDefinition, Metadata } from '@grpc/grpc-js';
import { loadSync } from '@grpc/proto-loader';
import { join } from 'path';

import { ServiceRegistryService } from '@common/service-registry.service';
import { TraceContext } from '@common/trace';

interface UnaryClient {
  close: () => void;
  [method: string]: unknown;
}

@Injectable()
export class GrpcClientsService implements OnModuleDestroy {
  private readonly sessionClient: UnaryClient;
  private readonly omsClient: UnaryClient;
  private readonly riskClient: UnaryClient;
  private readonly reportingClient: UnaryClient;

  constructor(private readonly registry: ServiceRegistryService) {
    const cfg = this.registry.getConfig();

    this.sessionClient = this.createClient(
      'qtrader.v1.session',
      'SessionService',
      join(__dirname, '../../../proto/v1/session.proto'),
      cfg.sessionControlGrpcUrl,
    );

    this.omsClient = this.createClient(
      'qtrader.v1.oms',
      'OmsService',
      join(__dirname, '../../../proto/v1/oms.proto'),
      cfg.omsWorkflowGrpcUrl,
    );

    this.riskClient = this.createClient(
      'qtrader.v1.risk',
      'RiskPolicyService',
      join(__dirname, '../../../proto/v1/risk.proto'),
      cfg.riskPolicyGrpcUrl,
    );

    this.reportingClient = this.createClient(
      'qtrader.v1.reporting',
      'ReportingService',
      join(__dirname, '../../../proto/v1/reporting.proto'),
      cfg.reportingQueryGrpcUrl,
    );
  }

  async onModuleDestroy(): Promise<void> {
    this.sessionClient.close();
    this.omsClient.close();
    this.riskClient.close();
    this.reportingClient.close();
  }

  async sessionStart(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.sessionClient, 'StartSession', payload, trace);
  }

  async sessionHalt(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.sessionClient, 'HaltSession', payload, trace);
  }

  async sessionStatus(trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.sessionClient, 'GetStatus', {}, trace);
  }

  async riskValidate(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.riskClient, 'ValidateOrder', payload, trace);
  }

  async omsCreate(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.omsClient, 'CreateOrder', payload, trace);
  }

  async omsTransition(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.omsClient, 'TransitionOrder', payload, trace);
  }

  async omsGet(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.omsClient, 'GetOrder', payload, trace);
  }

  async omsList(trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.omsClient, 'ListOrders', {}, trace);
  }

  async reportSummary(payload: Record<string, unknown>, trace: TraceContext): Promise<Record<string, unknown>> {
    return this.callUnary(this.reportingClient, 'GetSessionSummary', payload, trace);
  }

  private createClient(
    pkgName: string,
    serviceName: string,
    protoPath: string,
    url: string,
  ): UnaryClient {
    const pkgDef = loadSync(protoPath, {
      keepCase: true,
      longs: String,
      enums: String,
      defaults: true,
      oneofs: true,
    });
    const grpcPkg = loadPackageDefinition(pkgDef) as Record<string, unknown>;

    const namespace = pkgName.split('.').reduce((acc: unknown, key: string) => {
      return (acc as Record<string, unknown>)[key];
    }, grpcPkg) as Record<string, unknown>;

    const clientCtor = namespace[serviceName] as new (addr: string, creds: unknown) => UnaryClient;
    return new clientCtor(url, credentials.createInsecure());
  }

  private async callUnary(
    client: UnaryClient,
    methodName: string,
    payload: Record<string, unknown>,
    trace: TraceContext,
  ): Promise<Record<string, unknown>> {
    const metadata = new Metadata();
    metadata.set('x-trace-id', trace.traceId);
    metadata.set('x-session-id', trace.sessionId);

    return new Promise((resolve, reject) => {
      const fn = client[methodName] as (
        req: Record<string, unknown>,
        md: Metadata,
        cb: (err: Error | null, response: Record<string, unknown>) => void,
      ) => void;

      fn.call(client, payload, metadata, (err, response) => {
        if (err) {
          reject(err);
          return;
        }
        resolve(response);
      });
    });
  }
}
