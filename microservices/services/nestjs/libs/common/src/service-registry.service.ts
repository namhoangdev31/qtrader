import { Injectable } from '@nestjs/common';

import { ServiceRegistryConfig } from './types';

@Injectable()
export class ServiceRegistryService {
  getConfig(): ServiceRegistryConfig {
    return {
      sessionControlGrpcUrl: process.env.SESSION_CONTROL_GRPC_URL ?? 'session-control:50061',
      omsWorkflowGrpcUrl: process.env.OMS_WORKFLOW_GRPC_URL ?? 'oms-workflow:50062',
      riskPolicyGrpcUrl: process.env.RISK_POLICY_GRPC_URL ?? 'risk-policy:50063',
      reportingQueryGrpcUrl: process.env.REPORTING_QUERY_GRPC_URL ?? 'reporting-query:50064',
    };
  }
}
