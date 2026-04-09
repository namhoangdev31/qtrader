import { Injectable, Logger } from '@nestjs/common';

@Injectable()
export class JsonLoggerService {
  private readonly logger = new Logger(JsonLoggerService.name);

  log(event: string, payload: Record<string, unknown>): void {
    this.logger.log(
      JSON.stringify({
        level: 'info',
        event,
        ...payload,
      }),
    );
  }

  error(event: string, payload: Record<string, unknown>): void {
    this.logger.error(
      JSON.stringify({
        level: 'error',
        event,
        ...payload,
      }),
    );
  }
}
