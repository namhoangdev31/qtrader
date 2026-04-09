import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';

@Injectable()
export class TraceMiddleware implements NestMiddleware {
  /**
   * Control Plane: Ensure every request in the institutional platform
   * has a Trace ID and Session ID for Forensic Auditing.
   */
  use(req: Request, res: Response, next: NextFunction) {
    const traceId = req.headers['x-trace-id'] || uuidv4();
    const sessionId = req.headers['x-session-id'] || 'GLOBAL_IDLE';
    
    // Inject into request for downstream usage
    req['traceId'] = traceId;
    req['sessionId'] = sessionId;
    
    // Ensure response header carries it back
    res.setHeader('x-trace-id', traceId);
    next();
  }
}
