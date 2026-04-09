import { Body, Controller, Get, Post } from '@nestjs/common';

import { SessionService } from './session.service';

@Controller('session')
export class SessionController {
  constructor(private readonly sessionService: SessionService) {}

  @Post('start')
  async start(@Body() body: { sessionId?: string }): Promise<{ sessionId: string; status: string }> {
    return this.sessionService.startSession(body.sessionId);
  }

  @Post('halt')
  async halt(@Body() body: { reason?: string }): Promise<{ sessionId: string | null; status: string }> {
    return this.sessionService.haltSession(body.reason ?? 'MANUAL_HALT');
  }

  @Get('status')
  status(): { sessionId: string | null; status: 'IDLE' | 'ACTIVE' | 'HALTED' } {
    return this.sessionService.getStatus();
  }
}
