import { useState, useEffect, useCallback, useRef } from 'react';

export interface Portfolio {
  equity: number;
  cash: number;
  realized_pnl: number;
  total_commissions: number;
  positions: any[];
  trade_history: any[];
  current_price: number;
  timestamp: string;
  live_config: Record<string, any>;
}

export interface Forensics {
  ai_thinking: string;
  ai_explanation: string;
  module_traces: any;
  thinking_history: any[];
  timestamp: string;
}

export interface Telemetry {
  status: {
    running: boolean;
    mode: string;
    market_price?: number;
    session_id?: string;
    status?: string;
    stats?: Record<string, number>;
    error?: string;
  };
  latency_ms: number;
  is_synced: boolean;
  uptime_seconds: number;
  timestamp: string;
}

export const defaultPortfolio: Portfolio = {
  equity: 0,
  cash: 0,
  realized_pnl: 0,
  total_commissions: 0,
  positions: [],
  trade_history: [],
  current_price: 0,
  timestamp: '',
  live_config: {},
};

export interface AuditData {
  notes: any[];
  trades: any[];
  positions: any[];
  timestamp: string;
}

export const defaultAudit: AuditData = {
  notes: [],
  trades: [],
  positions: [],
  timestamp: '',
};

export function useTradingSystem() {
  const [portfolio, setPortfolio] = useState<Portfolio>(defaultPortfolio);
  const [forensics, setForensics] = useState<Forensics | null>(null);
  const [audit, setAudit] = useState<AuditData>(defaultAudit);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [activeSession, setActiveSession] = useState<any>(null);
  const [logs, setLogs] = useState<{ time: string; msg: string; type: string }[]>([]);

  const tradingWs = useRef<WebSocket | null>(null);
  const forensicWs = useRef<WebSocket | null>(null);
  const telemetryWs = useRef<WebSocket | null>(null);
  const auditWs = useRef<WebSocket | null>(null);

  const addLog = useCallback((msg: string, type: string = 'info') => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{ time, msg, type }, ...prev].slice(0, 50));
  }, []);

  const getWsUrl = useCallback(() => {
    return (typeof window !== 'undefined' && window.location.hostname === 'localhost')
      ? 'ws://localhost:8000'
      : 'ws://api_dashboard:8000';
  }, []);

  const getBaseUrl = useCallback(() => {
    return (typeof window !== 'undefined' && window.location.hostname === 'localhost')
      ? 'http://localhost:8000'
      : 'http://api_dashboard:8000';
  }, []);

  const connectAll = useCallback(() => {
    const wsUrl = getWsUrl();
    
    // 1. Simulation/Trading Socket
    tradingWs.current = new WebSocket(`${wsUrl}/ws/simulation`);
    tradingWs.current.onmessage = (e) => setPortfolio(JSON.parse(e.data));
    tradingWs.current.onopen = () => addLog('Simulation Stream: ONLINE', 'success');

    // 2. Forensics Socket
    forensicWs.current = new WebSocket(`${wsUrl}/ws/forensics`);
    forensicWs.current.onmessage = (e) => setForensics(JSON.parse(e.data));
    forensicWs.current.onopen = () => addLog('Forensic Stream: ONLINE', 'success');

    // 3. Telemetry Socket
    telemetryWs.current = new WebSocket(`${wsUrl}/ws/telemetry`);
    telemetryWs.current.onmessage = (e) => setTelemetry(JSON.parse(e.data));
    telemetryWs.current.onopen = () => addLog('Telemetry Stream: ONLINE', 'success');

    // 4. Audit Socket (Dedicated)
    auditWs.current = new WebSocket(`${wsUrl}/ws/audit`);
    auditWs.current.onmessage = (e) => setAudit(JSON.parse(e.data));
    auditWs.current.onopen = () => addLog('Audit Stream: ONLINE', 'success');

  }, [getWsUrl, addLog]);

  const disconnectAll = useCallback(() => {
    [tradingWs, forensicWs, telemetryWs, auditWs].forEach(ws => {
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    });
    addLog('All streams: DISCONNECTED', 'system');
  }, [addLog]);

  // Session Management (Manual Only)
  const handleStartSession = async (mode: 'live' | 'paper' = 'paper') => {
    try {
      // 1. Start Physical Session
      const res = await fetch(`${getBaseUrl()}/api/v1/sessions/start`, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      const data = await res.json();
      
      if (data.status === 'started') {
        setActiveSession(data);
        // 2. Start Logic Engine (Sim or Live)
        if (mode === 'paper') {
          await fetch(`${getBaseUrl()}/api/v1/sim/start`, { method: 'POST' });
        }
        // 3. Connect Sockets
        connectAll();
        addLog(`Session ${data.session_id} Initialized @ 100% Capacity`, 'success');
      }
    } catch (e: any) {
      addLog(`Initialization Failed: ${e.message}`, 'error');
    }
  };

  const handleSimReset = async () => {
    try {
      await fetch(`${getBaseUrl()}/api/v1/sim/reset`, { method: 'POST' });
      addLog('Simulation Reset to Base State', 'system');
      setPortfolio(defaultPortfolio);
    } catch (e: any) {
      addLog(`Reset Failed: ${e.message}`, 'error');
    }
  };

  const handleSimConfig = async (sl: number, tp: number) => {
    try {
      await fetch(`${getBaseUrl()}/api/v1/sim/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          initial_balance: 1000,
          sl_pct: sl / 100,
          tp_pct: tp / 100,
          tick_interval: 1.0,
          base_price: 50000,
        }),
      });
      addLog(`Simulation Configured: SL=${sl}% TP=${tp}%`, 'success');
    } catch (e: any) {
      addLog(`Config Update Failed: ${e.message}`, 'error');
    }
  };

  const handleStopSession = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/sessions/stop`, { method: 'POST' });
      const data = await res.json();
      setActiveSession(null);
      disconnectAll();
      addLog('Session Terminated. Analysis generated.', 'system');
      return data.report;
    } catch (e: any) {
      addLog(`Termination Error: ${e.message}`, 'error');
    }
  };

  const fetchSessionHistory = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/sessions/history?limit=20`);
      return await res.json();
    } catch (e: any) {
      addLog(`History Fetch Failed: ${e.message}`, 'error');
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    const syncActiveSession = async () => {
      try {
        const res = await fetch(`${getBaseUrl()}/api/v1/sessions/active`);
        const data = await res.json();
        if (data.active && data.session) {
          setActiveSession(data.session);
          connectAll();
          addLog(`Auto-synchronized with Active Session: ${data.session.session_id}`, 'success');
        }
      } catch (e) {
        // Silent fail on background sync
      }
    };

    syncActiveSession();
    return () => disconnectAll();
  }, [connectAll, disconnectAll, getBaseUrl, addLog]);

  return {
    portfolio,
    forensics,
    audit,
    telemetry,
    activeSession,
    logs,
    handleStartSession,
    handleStopSession,
    handleSimReset,
    handleSimConfig,
    fetchSessionHistory,
    addLog,
    getBaseUrl
  };
}
