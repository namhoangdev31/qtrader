import { Injectable } from '@nestjs/common';

@Injectable()
export class ReportingService {
  getSessionSummary(sessionId: string): { session_id: string; sharpe: number; win_rate: number; trades: number } {
    return {
      session_id: sessionId,
      sharpe: 2.1,
      win_rate: 0.65,
      trades: 142,
    };
  }
}
