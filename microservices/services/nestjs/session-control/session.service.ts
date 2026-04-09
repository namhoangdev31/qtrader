import { Injectable, Logger } from '@nestjs/common';

@Injectable()
export class SessionService {
  private readonly logger = new Logger(SessionService.name);
  private currentSessionId: string | null = null;
  private status: 'IDLE' | 'ACTIVE' | 'HALTED' = 'IDLE';

  async startSession(sessionId?: string): Promise<{ sessionId: string; status: string }> {
    const nextSessionId = sessionId ?? `sess_${Date.now()}`;
    this.logger.log(`Starting session: ${nextSessionId}`);
    this.currentSessionId = nextSessionId;
    this.status = 'ACTIVE';
    return { sessionId: nextSessionId, status: this.status };
  }

  async haltSession(reason: string): Promise<{ sessionId: string | null; status: string }> {
    this.logger.warn(`HALTING session: ${this.currentSessionId} | Reason: ${reason}`);
    this.status = 'HALTED';
    return { sessionId: this.currentSessionId, status: this.status };
  }

  getStatus(): { sessionId: string | null; status: 'IDLE' | 'ACTIVE' | 'HALTED' } {
    return { sessionId: this.currentSessionId, status: this.status };
  }
}
