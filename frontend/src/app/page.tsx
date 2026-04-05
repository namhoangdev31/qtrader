"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { TradingChart } from '@/components/TradingChart';
import { OrderPanel } from '@/components/OrderPanel';
import { PositionsTable } from '@/components/PositionsTable';
import { ShieldCheck, Zap, Globe, MessageSquare } from 'lucide-react';

export default function Dashboard() {
  const [positions, setPositions] = useState<any[]>([]);
  const [systemStatus, setSystemStatus] = useState({ running: false, mode: 'OFFLINE' });
  const [logs, setLogs] = useState<{ time: string; msg: string; type: string }[]>([]);
  const [liveStats, setLiveStats] = useState({ price: 0, bid: 0, ask: 0, vol: 0 });
  
  const addLog = useCallback((msg: string, type: string = 'info') => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{ time, msg, type }, ...prev].slice(0, 50));
  }, []);

  // API Calls
  const fetchStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/status');
      if (res.ok) {
        const data = await res.json();
        setSystemStatus({ running: data.running, mode: data.mode });
      }
    } catch (e) {
      setSystemStatus({ running: false, mode: 'OFFLINE' });
    }
  };

  const fetchPositions = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/positions');
      if (res.ok) {
        const data = await res.json();
        setPositions(data);
      }
    } catch (e) {}
  };

  const submitOrder = async (side: 'BUY' | 'SELL', qty: number) => {
    addLog(`Submitting ${side} order for ${qty} BTC...`, 'system');
    try {
      const res = await fetch('http://localhost:8000/api/v1/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: 'BTC-USD',
          side,
          quantity: qty,
          order_type: 'MARKET'
        })
      });
      const data = await res.json();
      if (res.ok) {
        addLog(`Order successful: ${data.order_id}`, 'success');
        fetchPositions();
      } else {
        addLog(`Order failed: ${data.detail || 'Unknown error'}`, 'error');
      }
    } catch (e: any) {
      addLog(`Execution error: ${e.message}`, 'error');
    }
  };

  // WebSocket Setup
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/market/BTC-USD');
    
    ws.onopen = () => addLog('WebSocket connected to Engine.', 'success');
    
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (!msg.price) return;

        const p = parseFloat(msg.price);
        setLiveStats({
          price: p,
          bid: parseFloat(msg.best_bid || 0),
          ask: parseFloat(msg.best_ask || 0),
          vol: parseFloat(msg.volume_24h || 0)
        });
      } catch (e) {}
    };

    ws.onclose = () => {
      addLog('WebSocket disconnected. Retrying...', 'error');
    };

    // Polling for status/positions
    fetchStatus();
    fetchPositions();
    const interval = setInterval(() => {
      fetchStatus();
      fetchPositions();
    }, 5000);

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, [addLog]);

  return (
    <main className="min-h-screen p-4 lg:p-8 max-w-[1600px] mx-auto space-y-6">
      {/* HEADER */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-[#1e222d] pb-6">
        <div className="flex items-center gap-4">
          <div className="bg-[#2962ff] p-2 rounded-lg shadow-lg shadow-blue-900/40">
            <Zap className="text-white fill-white" size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              QTRADER <span className="text-slate-500 font-normal">| Institutional Engine</span>
            </h1>
            <div className="flex items-center gap-4 mt-1">
              <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                <ShieldCheck size={14} /> SECURE GATEWAY
              </span>
              <span className="flex items-center gap-1.5 text-xs font-medium text-blue-400">
                <Globe size={14} /> GLOBAL LIQUIDITY
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className={`px-4 py-1.5 rounded-full border text-xs font-bold flex items-center gap-2 ${
            systemStatus.running ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400' : 'bg-rose-500/10 border-rose-500/50 text-rose-400'
          }`}>
            <div className={`w-2 h-2 rounded-full ${systemStatus.running ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
            {systemStatus.running ? `RUNNING: ${systemStatus.mode}` : 'OFFLINE'}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COMPONENT: CHART & STATS */}
        <div className="lg:col-span-9 space-y-6">
          {/* STATS STRIP */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Live Price" value={`$${liveStats.price.toLocaleString()}`} accent="blue" />
            <StatCard label="Spread" value={(liveStats.ask - liveStats.bid).toFixed(2)} accent="slate" />
            <StatCard label="24h Volume" value={`${liveStats.vol.toFixed(2)} BTC`} accent="slate" />
            <StatCard label="Order Book" value={`${liveStats.bid.toFixed(2)} / ${liveStats.ask.toFixed(2)}`} accent="slate" />
          </div>

          <div className="relative">
            <TradingChart />
          </div>

          {/* POSITIONS */}
          <PositionsTable positions={positions} />
        </div>

        {/* RIGHT COMPONENT: ORDER & LOGS */}
        <div className="lg:col-span-3 space-y-6">
          <OrderPanel onOrder={submitOrder} />
          
          {/* ACTIVITY LOGS */}
          <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-4 flex flex-col h-[400px]">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-[#1e222d] text-slate-400">
              <MessageSquare size={16} />
              <span className="text-xs font-bold uppercase">Activity Log</span>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 pr-2 text-[11px] font-mono scrollbar-hide">
              {logs.map((log, i) => (
                <div key={i} className="flex gap-2 leading-relaxed animate-in fade-in slide-in-from-left-2 duration-300">
                  <span className="text-slate-500 whitespace-nowrap">[{log.time}]</span>
                  <span className={
                    log.type === 'success' ? 'text-emerald-400' : 
                    log.type === 'error' ? 'text-rose-400' : 
                    log.type === 'system' ? 'text-blue-400' : 'text-slate-300'
                  }>
                    {log.msg}
                  </span>
                </div>
              ))}
              {logs.length === 0 && (
                <div className="h-full flex items-center justify-center text-slate-600 italic">
                  Waiting for events...
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

function StatCard({ label, value, accent }: { label: string, value: string, accent: 'blue' | 'slate' }) {
  return (
    <div className="bg-[#161a25] border border-[#1e222d] p-4 rounded-lg shadow-lg">
      <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-bold ${accent === 'blue' ? 'text-[#2962ff]' : 'text-slate-200'}`}>{value}</p>
    </div>
  );
}
