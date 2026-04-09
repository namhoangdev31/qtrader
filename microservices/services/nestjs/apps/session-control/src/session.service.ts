import { Injectable } from '@nestjs/common';

import { DEFAULT_SESSION_ID } from '@common/constants';

export type SessionStatus = 'IDLE' | 'ACTIVE' | 'HALTED';

@Injectable()
export class SessionService {
  private currentSessionId: string = DEFAULT_SESSION_ID;
  private status: SessionStatus = 'IDLE';

  startSession(sessionId?: string): { session_id: string; status: SessionStatus } {
    this.currentSessionId = sessionId && sessionId.trim().length > 0 ? sessionId : `sess_${Date.now()}`;
    this.status = 'ACTIVE';
    return { session_id: this.currentSessionId, status: this.status };
  }

  haltSession(_reason: string): { session_id: string; status: SessionStatus } {
    this.status = 'HALTED';
    return { session_id: this.currentSessionId, status: this.status };
  }

  getStatus(): { session_id: string; status: SessionStatus } {
    return { session_id: this.currentSessionId, status: this.status };
  }
}
