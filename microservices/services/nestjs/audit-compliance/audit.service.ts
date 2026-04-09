import { Injectable, Logger } from '@nestjs/common';

@Injectable()
export class AuditService {
  private readonly logger = new Logger(AuditService.name);

  async logForensicNote(
    note: string,
    traceId: string,
    level: 'INFO' | 'ALERT' | 'CRITICAL',
  ): Promise<{ note: string; traceId: string; level: string }> {
    this.logger.log(`[AUDIT] Recording ${level} note | Trace: ${traceId} | ${note}`);
    return { note, traceId, level };
  }
}
