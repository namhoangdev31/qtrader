import { Metadata } from '@grpc/grpc-js';
import { randomUUID } from 'crypto';

import { DEFAULT_SESSION_ID } from './constants';

export interface TraceContext {
  traceId: string;
  sessionId: string;
}

export function resolveTraceFromHeaders(
  traceIdHeader?: string,
  sessionIdHeader?: string,
): TraceContext {
  return {
    traceId: traceIdHeader ?? randomUUID(),
    sessionId: sessionIdHeader ?? DEFAULT_SESSION_ID,
  };
}

export function grpcMetadataFromTrace(ctx: TraceContext): Metadata {
  const md = new Metadata();
  md.set('x-trace-id', ctx.traceId);
  md.set('x-session-id', ctx.sessionId);
  return md;
}
