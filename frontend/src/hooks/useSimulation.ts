import { useState, useEffect, useCallback } from 'react';

export interface SimSnapshot {
  equity: number;
  cash: number;
  realized_pnl: number;
  total_commissions: number;
  total_gross_pnl: number;
  current_price: number;
  open_positions: any[];
  trade_history: any[];
  ai_thinking?: string;
  ai_explanation?: string;
  thinking_history?: any[];
  live_trace?: any;
  adaptive: {
    stop_loss_pct: number;
    take_profit_pct: number;
    position_size_pct: number;
    win_rate: number;
    total_wins: number;
    total_losses: number;
    win_streak: number;
    loss_streak: number;
    expected_value: number;
    max_drawdown_pct: number;
    total_trades: number;
  };
  peak_equity: number;
  max_drawdown: number;
  position_value: number;
}

export const defaultSimSnapshot: SimSnapshot = {
  equity: 1000,
  cash: 1000,
  realized_pnl: 0,
  total_commissions: 0,
  total_gross_pnl: 0,
  current_price: 50000,
  open_positions: [],
  trade_history: [],
  ai_thinking: "Awaiting first analysis...",
  ai_explanation: "Simulation engine is initializing market data buffer...",
  thinking_history: [],
  live_trace: null,
  adaptive: {
    stop_loss_pct: 2.0,
    take_profit_pct: 3.0,
    position_size_pct: 10.0,
    win_rate: 0,
    total_wins: 0,
    total_losses: 0,
    win_streak: 0,
    loss_streak: 0,
    expected_value: 0,
    max_drawdown_pct: 0,
    total_trades: 0,
  },
  peak_equity: 1000,
  max_drawdown: 0,
  position_value: 0,
};

export function useSimulation() {
  const [simSnapshot, setSimSnapshot] = useState<SimSnapshot>(defaultSimSnapshot);
  const [simRunning, setSimRunning] = useState(false);
  const [logs, setLogs] = useState<{ time: string; msg: string; type: string }[]>([]);
  const [activeSession, setActiveSession] = useState<any>(null);
  const [sessionHistory, setSessionHistory] = useState<any[]>([]);

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

  // Simulation WebSocket
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimeout: NodeJS.Timeout | null = null;
    let retryCount = 0;
    const MAX_RETRIES = 50;
    const BASE_RETRY_MS = 2000;

    const connect = () => {
      if (retryCount >= MAX_RETRIES) {
        addLog('Max Simulation WS retries reached.', 'error');
        return;
      }

      const wsUrl = `${getWsUrl()}/ws/simulation`;
      ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        retryCount = 0;
        addLog('Simulation WebSocket connected.', 'success');
        setSimRunning(true);
      };
      

      ws.onclose = () => {
        setSimRunning(false);
        retryCount++;
        retryTimeout = setTimeout(connect, BASE_RETRY_MS);
      };

      ws.onerror = () => {
        addLog('Simulation WS connection error.', 'error');
      };
    };

    connect();

    return () => {
      if (retryTimeout) clearTimeout(retryTimeout);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [addLog, getWsUrl]);

  // Session Management
  useEffect(() => {
    const checkActiveSession = async () => {
      try {
        const res = await fetch(`${getBaseUrl()}/api/v1/sessions/active`);
        const data = await res.json();
        if (data.active) {
          setActiveSession(data.session);
        }
      } catch (e) {
        // ignore
      }
    };
    checkActiveSession();
  }, [getBaseUrl]);

  const handleSimStart = async () => {
    try {
      await fetch(`${getBaseUrl()}/api/v1/sim/start`, { method: 'POST' });
      addLog('Simulation started', 'success');
      if (!activeSession) {
        await startTradingSession();
      }
    } catch (e: any) {
      addLog(`Failed to start simulation: ${e.message}`, 'error');
    }
  };

  const startTradingSession = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/sessions/start`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'started') {
        setActiveSession({ session_id: data.session_id, status: 'ACTIVE', start_time: new Date().toISOString() });
        addLog(`Trading Session Started: ${data.session_id}`, 'success');
      }
    } catch (e: any) {
      addLog(`Failed to start session: ${e.message}`, 'error');
    }
  };

  const handleSimStop = async () => {
    try {
      await fetch(`${getBaseUrl()}/api/v1/sim/stop`, { method: 'POST' });
      addLog('Trading stopped', 'system');
      setSimRunning(false);
      
      if (activeSession) {
        return await stopTradingSession();
      }
      
      await handleSimReset();
    } catch (e: any) {
      addLog(`Failed to stop trading: ${e.message}`, 'error');
    }
  };

  const stopTradingSession = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/sessions/stop`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'completed') {
        setActiveSession(null);
        addLog(`Trading Session Completed. Analysis ready.`, 'success');
        return data.report;
      }
    } catch (e: any) {
      addLog(`Failed to stop session: ${e.message}`, 'error');
    }
  };

  const handleSimReset = async () => {
    try {
      await fetch(`${getBaseUrl()}/api/v1/sim/reset`, { method: 'POST' });
      addLog('Simulation reset', 'system');
      setSimSnapshot(defaultSimSnapshot);
    } catch (e: any) {
      addLog(`Failed to reset simulation: ${e.message}`, 'error');
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
      addLog(`Config updated: SL=${sl}% TP=${tp}%`, 'success');
    } catch (e: any) {
      addLog(`Failed to update config: ${e.message}`, 'error');
    }
  };

  const fetchSessionHistory = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/sessions/history?limit=20`);
      const data = await res.json();
      setSessionHistory(data);
      return data;
    } catch (e: any) {
      addLog(`Failed to fetch session history: ${e.message}`, 'error');
    }
  };

  return {
    simSnapshot,
    simRunning,
    logs,
    activeSession,
    sessionHistory,
    addLog,
    handleSimStart,
    handleSimStop,
    handleSimReset,
    handleSimConfig,
    fetchSessionHistory,
    getBaseUrl,
    getWsUrl
  };
}
