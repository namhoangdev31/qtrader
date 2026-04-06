"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { TradingChart } from '@/components/TradingChart';
import { OrderPanel } from '@/components/OrderPanel';
import { SimPositionsTable } from '@/components/SimPositionsTable';
import { TradeHistory } from '@/components/TradeHistory';
import { PnLStats } from '@/components/PnLStats';
import { SimControlPanel } from '@/components/SimControlPanel';
import { SessionReportModal } from '@/components/SessionReportModal';
import { SessionHistoryModal } from '@/components/SessionHistoryModal';
import { useSimulation } from '@/hooks/useSimulation';
import { 
  Play, 
  Square, 
  Zap, 
  History, 
  Activity, 
  MessageSquare,
  Bot,
  LayoutDashboard,
  ShieldCheck,
  Globe,
  Award
} from 'lucide-react';
import Link from 'next/link';

export default function Dashboard() {
  const {
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
  } = useSimulation();

  const [positions, setPositions] = useState<any[]>([]);
  const [systemStatus, setSystemStatus] = useState({ running: false, mode: 'OFFLINE' });
  const [pnlSummary, setPnlSummary] = useState({ total_equity: 100000, realized_pnl: 0, total_commissions: 0 });
  
  const [showSessionReport, setShowSessionReport] = useState(false);
  const [sessionReport, setSessionReport] = useState<any>(null);
  const [showSessionHistory, setShowSessionHistory] = useState(false);
  const [activeTab, setActiveTab] = useState<'chart' | 'trades'>('chart');

  const submitOrder = async (side: 'BUY' | 'SELL', qty: number) => {
    addLog(`Submitting ${side} order for ${qty} BTC...`, 'system');
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/order`, {
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
      } else {
        addLog(`Order failed: ${data.detail || 'Unknown error'}`, 'error');
      }
    } catch (e: any) {
      addLog(`Execution error: ${e.message}`, 'error');
    }
  };

  // Trading WebSocket (legacy/non-sim)
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimeout: NodeJS.Timeout | null = null;
    let retryCount = 0;
    const MAX_RETRIES = 50;
    const BASE_RETRY_MS = 2000;

    const connect = () => {
      if (retryCount >= MAX_RETRIES) return;

      const wsUrl = `${getWsUrl()}/ws/trading`;
      ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        retryCount = 0;
      };
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.status) {
            setSystemStatus({ running: msg.status.running, mode: msg.status.mode });
          }
          if (msg.positions) {
            setPositions(msg.positions);
          }
          if (msg.pnl_summary) {
            setPnlSummary(msg.pnl_summary);
          }
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        retryCount++;
        retryTimeout = setTimeout(connect, BASE_RETRY_MS);
      };

      ws.onerror = () => {};
    };

    connect();

    return () => {
      if (retryTimeout) clearTimeout(retryTimeout);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [getWsUrl]);

  const handleViewHistory = async () => {
    await fetchSessionHistory();
    setShowSessionHistory(true);
  };

  const handleSelectHistoricalSession = (session: any) => {
    setSessionReport(session.summary);
    setShowSessionReport(true);
  };

  const totalSessionPnl = simSnapshot.equity - 1000;
  const isSessionActive = activeSession || simRunning;

  return (
    <main className="min-h-screen p-4 lg:p-8 max-w-[1800px] mx-auto space-y-6">
      {/* HEADER */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-[#1e222d] pb-6">
        <div className="flex items-center gap-4">
          <div className="bg-[#2962ff] p-2 rounded-lg shadow-lg shadow-blue-900/40">
            <Zap className="text-white fill-white" size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              QTRADER <span className="text-slate-500 font-normal">| Simulation Dashboard</span>
            </h1>
            <div className="flex items-center gap-4 mt-1">
              <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                <ShieldCheck size={14} /> SECURE GATEWAY
              </span>
              <span className="flex items-center gap-1.5 text-xs font-medium text-blue-400">
                <Globe size={14} /> GLOBAL LIQUIDITY
              </span>
              <span className="flex items-center gap-1.5 text-xs font-medium text-amber-400">
                <Activity size={14} /> SIMULATION MODE
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/expert"
            className="bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 px-4 py-2 rounded-lg font-black text-[10px] uppercase tracking-widest flex items-center gap-2 border border-blue-500/30 transition-all"
          >
            <LayoutDashboard size={14} /> Expert View
          </Link>

          <button 
            onClick={handleViewHistory}
            className="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-black text-[10px] uppercase tracking-widest flex items-center gap-2 border border-[#1e222d] transition-all"
          >
            <History size={14} /> Audit history
          </button>
          
          {isSessionActive ? (
            <button 
              onClick={handleSimStop}
              className="bg-rose-500 hover:bg-rose-400 text-white px-4 py-2 rounded-lg font-bold text-xs flex items-center gap-2 shadow-lg shadow-rose-900/20 active:scale-95 transition-all"
            >
              <Square size={14} fill="currentColor" /> STOP TRADING
            </button>
          ) : (
            <button 
              onClick={handleSimStart}
              className="bg-[#2962ff] hover:bg-[#1e50e0] text-white px-4 py-2 rounded-lg font-bold text-xs flex items-center gap-2 shadow-lg shadow-blue-900/20 active:scale-95 transition-all"
            >
              <Play size={14} fill="currentColor" /> START TRADING
            </button>
          )}
          <div className={`px-4 py-1.5 rounded-full border text-xs font-bold flex items-center gap-2 ${
            isSessionActive ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400' : 'bg-slate-700/50 border-slate-600/50 text-slate-400'
          }`}>
            <div className={`w-2 h-2 rounded-full ${isSessionActive ? 'bg-emerald-400 animate-pulse' : 'bg-slate-50'}`} />
            {isSessionActive ? 'TRADING ACTIVE' : 'SYSTEM OFFLINE'}
          </div>
        </div>
      </header>

      {/* STATS STRIP */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Equity" value={`$${simSnapshot.equity.toFixed(2)}`} accent={totalSessionPnl >= 0 ? "blue" : "rose"} />
        <StatCard label="Session PnL" value={`${totalSessionPnl >= 0 ? '+' : ''}$${totalSessionPnl.toFixed(2)}`} accent={totalSessionPnl >= 0 ? "blue" : "rose"} />
        <StatCard label="Win Rate" value={`${simSnapshot.adaptive.win_rate.toFixed(1)}%`} accent="slate" />
        <StatCard label="Total Trades" value={`${simSnapshot.adaptive.total_trades}`} accent="slate" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT: Chart / Trades / Positions */}
        <div className="lg:col-span-8 space-y-6">
          {/* Tab Switcher */}
          <div className="flex items-center gap-2 bg-[#161a25] border border-[#1e222d] rounded-lg p-1.5">
            <button
              onClick={() => setActiveTab('chart')}
              className={`flex-1 py-2 rounded text-xs font-bold transition-all ${
                activeTab === 'chart' 
                  ? 'bg-[#2962ff] text-white shadow-lg shadow-blue-900/30' 
                  : 'text-slate-400 hover:text-slate-300 hover:bg-[#1e222d]'
              }`}
            >
              Chart & Positions
            </button>
            <button
              onClick={() => setActiveTab('trades')}
              className={`flex-1 py-2 rounded text-xs font-bold transition-all ${
                activeTab === 'trades' 
                  ? 'bg-[#2962ff] text-white shadow-lg shadow-blue-900/30' 
                  : 'text-slate-400 hover:text-slate-300 hover:bg-[#1e222d]'
              }`}
            >
              Trade History ({simSnapshot.trade_history.length})
            </button>
          </div>

          {activeTab === 'chart' ? (
            <>
              <div className="relative">
                <TradingChart />
              </div>
              <SimPositionsTable positions={simSnapshot.open_positions} />
              
               {/* PREMIUM AI THINKING STREAM (CHAT STYLE) */}
               <div className="bg-[#161a25] border border-[#2962ff]/30 rounded-xl shadow-2xl relative overflow-hidden group flex flex-col h-[600px]">
                 {/* Header */}
                 <div className="px-6 py-4 border-b border-[#1e222d] bg-black/20 flex items-center justify-between sticky top-0 z-20 backdrop-blur-md">
                   <div className="flex items-center gap-3">
                     <div className="relative">
                       <div className="w-3 h-3 rounded-full bg-blue-500 animate-ping absolute inset-0" />
                       <div className="w-3 h-3 rounded-full bg-blue-500 relative z-10" />
                     </div>
                     <h3 className="text-sm font-black uppercase tracking-[0.2em] text-blue-400">Tactical Thinking Stream</h3>
                   </div>
                   <div className="flex items-center gap-2">
                     <span className="text-[10px] font-bold text-slate-500 bg-slate-800/50 px-2 py-1 rounded border border-white/5">
                       MODEL: ATOMIC TRIO
                     </span>
                     <Bot size={16} className="text-blue-400/50" />
                   </div>
                 </div>

                 {/* Message Stream */}
                 <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide bg-[radial-gradient(circle_at_top_right,rgba(41,98,255,0.05),transparent)]">
                   {simSnapshot.thinking_history?.slice().reverse().map((th: any, i: number) => (
                     <div key={i} className="flex gap-4 group/msg animate-in fade-in slide-in-from-bottom-4 duration-500">
                       {/* AI Avatar Column */}
                       <div className="flex-shrink-0 mt-1">
                         <div className={`p-2 rounded-xl border ${
                           th.action === 'BUY' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                           th.action === 'SELL' ? 'bg-rose-500/10 border-rose-500/20 text-rose-400' :
                           'bg-blue-500/10 border-blue-500/20 text-blue-400'
                         }`}>
                           <Zap size={16} />
                         </div>
                       </div>

                       {/* Message Content Bubble */}
                       <div className="flex-1 space-y-2">
                         <div className="flex items-center gap-3">
                           <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Signal Analyst</span>
                           <span className="text-[9px] font-mono text-slate-600">
                             {new Date(th.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                           </span>
                           
                           {/* Tactical Badges */}
                           <div className="flex items-center gap-2 ml-auto">
                              <div className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter border ${
                                th.action === 'BUY' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                th.action === 'SELL' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
                                'bg-slate-800 text-slate-500 border-white/5'
                              }`}>
                                {th.action}
                              </div>
                              <div className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[9px] font-black uppercase">
                                {th.confidence} CONF
                              </div>
                           </div>
                         </div>

                         <div className="bg-white/[0.03] border border-white/[0.05] rounded-2xl rounded-tl-none p-4 shadow-sm hover:border-blue-500/30 transition-all">
                           {/* Human Narrative */}
                           <p className="text-sm text-slate-200 leading-relaxed mb-3">
                             {th.explanation || "No narrative explanation provided for this signal."}
                           </p>
                           
                           {/* Technical Logic Block */}
                           <div className="bg-black/40 rounded-lg p-3 border border-white/5 font-mono text-[11px] text-blue-300/80 leading-snug">
                             <div className="flex items-center gap-2 mb-1.5 opacity-50">
                               <MessageSquare size={12} />
                               <span className="text-[9px] font-black uppercase">Technical Footprint</span>
                             </div>
                             {th.thinking}
                           </div>
                         </div>
                       </div>
                     </div>
                   ))}

                   {(!simSnapshot.thinking_history || simSnapshot.thinking_history.length === 0) && (
                     <div className="h-full flex flex-col items-center justify-center space-y-4 opacity-30">
                       <Zap size={40} className="text-blue-500 animate-pulse" />
                       <p className="text-sm font-black uppercase tracking-[0.3em] text-slate-500">Awaiting Signal Sequence</p>
                     </div>
                   )}
                 </div>
               </div>
            </>
          ) : (
            <TradeHistory trades={simSnapshot.trade_history} />
          )}
        </div>

        {/* RIGHT: Control Panel / Stats / Logs */}
        <div className="lg:col-span-4 space-y-6">
          {/* SESSION STATUS WIDGET */}
          {activeSession && (
            <div className="bg-gradient-to-br from-[#2962ff]/20 to-[#161a25] border border-[#2962ff]/30 rounded-lg p-5 animate-in slide-in-from-right duration-500 relative overflow-hidden">
               <div className="absolute top-0 right-0 p-4 opacity-10">
                 <Award className="text-blue-400" size={60} />
               </div>
               <div className="flex items-center gap-3 mb-4">
                 <div className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
                 <h3 className="text-xs font-bold uppercase tracking-widest text-blue-400">Active Trading Session</h3>
               </div>
               <p className="text-[10px] font-mono text-slate-500 mb-4">{activeSession.session_id}</p>
               <div className="flex items-center justify-between">
                 <span className="text-[10px] font-bold text-slate-400">TIME RUNNING</span>
                 <span className="text-sm font-mono font-bold text-white tracking-widest">
                   {new Date(activeSession.start_time).toLocaleTimeString()}
                 </span>
               </div>
            </div>
          )}

          <SimControlPanel
            slPct={simSnapshot.adaptive.stop_loss_pct}
            tpPct={simSnapshot.adaptive.take_profit_pct}
            onConfigChange={handleSimConfig}
          />

          <PnLStats
            equity={simSnapshot.equity}
            cash={simSnapshot.cash}
            realizedPnl={simSnapshot.realized_pnl}
            totalGrossPnl={simSnapshot.total_gross_pnl}
            positionValue={simSnapshot.position_value}
            totalCommissions={simSnapshot.total_commissions}
            currentPrice={simSnapshot.current_price}
            peakEquity={simSnapshot.peak_equity}
            maxDrawdown={simSnapshot.max_drawdown}
            adaptive={simSnapshot.adaptive}
          />

          <OrderPanel onOrder={submitOrder} />
          

          {/* ACTIVITY LOGS */}
          <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-4 flex flex-col h-[300px]">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-[#1e222d] text-slate-400">
              <MessageSquare size={16} />
              <span className="text-xs font-bold uppercase">Activity Log</span>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 pr-2 text-[11px] font-mono scrollbar-hide">
              {logs.map((log: { time: string, type: string, msg: string }, i: number) => (
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

      {showSessionReport && (
        <SessionReportModal 
          report={sessionReport} 
          onClose={() => setShowSessionReport(false)} 
        />
      )}

      {showSessionHistory && (
        <SessionHistoryModal
          history={sessionHistory}
          onClose={() => setShowSessionHistory(false)}
          onViewReport={handleSelectHistoricalSession}
        />
      )}
    </main>
  );
}

function StatCard({ label, value, accent }: { label: string, value: string, accent: 'blue' | 'slate' | 'rose' }) {
  return (
    <div className="bg-[#161a25] border border-[#1e222d] p-4 rounded-lg shadow-lg">
      <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-bold ${accent === 'blue' ? 'text-[#2962ff]' : accent === 'rose' ? 'text-rose-400' : 'text-slate-200'}`}>{value}</p>
    </div>
  );
}
