import { Injectable, Logger } from '@nestjs/common';
import { randomUUID } from 'crypto';

@Injectable()
export class EventBusAdapter {
  private readonly logger = new Logger(EventBusAdapter.name);

  async wrapEvent(
    payload: unknown,
    type: string,
    traceId: string,
  ): Promise<{ eventId: string; traceId: string; timestampNs: number; payloadType: string; payload: unknown }> {
    this.logger.log(`[EVENT-BUS] Wrapping ${type} event | Trace: ${traceId}`);

    return {
      eventId: randomUUID(),
      traceId,
      timestampNs: Date.now() * 1_000_000,
      payloadType: type,
      payload,
    };
  }
}
