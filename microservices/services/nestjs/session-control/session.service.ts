import { Injectable, Logger } from '@nestjs/common';

@Injectable()
export class SessionService {
  private readonly logger = new Logger(SessionService.name);
  private currentSessionId: string | null = null;
  private status: 'IDLE' | 'ACTIVE' | 'HALTED' = 'IDLE';

  /**
   * Control Plane: Manage the lifecycle of a trading session.
   * Ensures that Compute Plane services are only active when a session is valid.
   */
  async startSession(sessionId: string): Promise<void> {
    this.logger.log(`Starting session: ${sessionId}`);
    this.currentSessionId = sessionId;
    this.status = 'ACTIVE';
    // Logic: Broadcast SESSION_START event to Python services
  }

  async haltSession(reason: string): Promise<void> {
    this.logger.warn(`HALTING session: ${this.currentSessionId} | Reason: ${reason}`);
    this.status = 'HALTED';
    // Logic: Trigger Kill-Switch command
  }

  getStatus() {
    return { sessionId: this.currentSessionId, status: this.status };
  }
}
