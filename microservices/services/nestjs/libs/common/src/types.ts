export type HealthStatus = 'ok' | 'degraded';

export interface HealthPayload {
  service: string;
  status: HealthStatus;
  timestamp: string;
}

export interface MetricsPayload {
  service: string;
  uptime_sec: number;
  counters: Record<string, number>;
}

export interface ServiceRegistryConfig {
  sessionControlGrpcUrl: string;
  omsWorkflowGrpcUrl: string;
  riskPolicyGrpcUrl: string;
  reportingQueryGrpcUrl: string;
}
