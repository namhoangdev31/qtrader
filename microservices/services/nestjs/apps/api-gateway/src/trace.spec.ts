import { resolveTraceFromHeaders } from '@common/trace';

describe('Trace propagation', () => {
  it('uses provided headers', () => {
    const trace = resolveTraceFromHeaders('trace-1', 'session-1');
    expect(trace.traceId).toBe('trace-1');
    expect(trace.sessionId).toBe('session-1');
  });

  it('generates defaults when missing', () => {
    const trace = resolveTraceFromHeaders(undefined, undefined);
    expect(trace.traceId.length).toBeGreaterThan(0);
    expect(trace.sessionId).toBe('GLOBAL_IDLE');
  });
});
