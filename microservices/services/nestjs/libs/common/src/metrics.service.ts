import { Injectable } from '@nestjs/common';

import { MetricsPayload } from './types';

@Injectable()
export class MetricsService {
  private readonly startedAt = Date.now();
  private readonly counters: Record<string, number> = {};

  increment(key: string, value = 1): void {
    this.counters[key] = (this.counters[key] ?? 0) + value;
  }

  snapshot(service: string): MetricsPayload {
    return {
      service,
      uptime_sec: Math.floor((Date.now() - this.startedAt) / 1000),
      counters: this.counters,
    };
  }
}
