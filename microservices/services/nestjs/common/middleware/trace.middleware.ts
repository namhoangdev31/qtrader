import { Injectable, NestMiddleware } from '@nestjs/common';
import { NextFunction, Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';

type TracedRequest = Request & { traceId: string; sessionId: string };

@Injectable()
export class TraceMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction): void {
    const traceIdHeader = req.headers['x-trace-id'];
    const sessionIdHeader = req.headers['x-session-id'];

    const traceId = typeof traceIdHeader === 'string' ? traceIdHeader : uuidv4();
    const sessionId = typeof sessionIdHeader === 'string' ? sessionIdHeader : 'GLOBAL_IDLE';

    const tracedReq = req as TracedRequest;
    tracedReq.traceId = traceId;
    tracedReq.sessionId = sessionId;

    res.setHeader('x-trace-id', traceId);
    next();
  }
}
