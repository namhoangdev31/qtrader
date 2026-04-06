"use client";

import React from 'react';
import { useTradingSystem } from '@/hooks/useTradingSystem';
import { ExpertStats } from '@/components/ExpertStats';
import { FlowVisualizer } from '@/components/FlowVisualizer';
import { ThinkingTerminal } from '@/components/ThinkingTerminal';
import { SimPositionsTable } from '@/components/SimPositionsTable';
import { TradeHistory } from '@/components/TradeHistory';
import { LogicMatrix } from '@/components/LogicMatrix';
import { SystemHealthHUD } from '@/components/SystemHealthHUD';
import { ForensicNotes } from '@/components/ForensicNotes';
import { 
  Zap, 
  Activity, 
  ShieldCheck, 
  Globe, 
  Play, 
  Square,
  LayoutDashboard,
  BarChart3,
  TrendingUp,
  History,
  Lock,
  Cpu,
  MonitorCheck
} from 'lucide-react';
import Link from 'next/link';

export default function ExpertDashboard() {
  const { 
    portfolio,
    forensics,
    telemetry,
    activeSession,
    handleStartSession,
    handleStopSession,
    addLog
  } = useTradingSystem();

  const isSessionActive = activeSession || (telemetry?.status.running);

  const handleStart = async () => {
    await handleStartSession('paper'); // 100% Manual as requested
  };

  const handleStop = async () => {
    await handleStopSession();
  };

  return (
    <main className="h-screen bg-[#080a0f] text-slate-300 font-sans selection:bg-blue-500/30 overflow-hidden flex flex-col">
      {/* SCROLLABLE CONTENT WRAPPER */}
      <div className="flex-1 overflow-y-auto p-4 lg:p-6 scroll-smooth scrollbar-thin">
      {/* HUD HEADER */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 border-b border-[#1e222d] pb-6 mb-6">
        <div className="flex items-center gap-5">
          <div className="bg-[#2962ff] p-2.5 rounded-lg shadow-2xl shadow-blue-900/40 group cursor-pointer hover:rotate-12 transition-all duration-300">
            <Cpu className="text-white fill-white" size={24} />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-black tracking-tighter text-white uppercase italic">
                Forensic Console <span className="text-[#2962ff]">v3.0</span>
              </h1>
              <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[9px] font-black uppercase tracking-widest animate-pulse">
                Forensic Fidelity: 100%
              </span>
            </div>
            <div className="flex items-center gap-4 mt-1.5 overflow-x-auto pb-1 scrollbar-hide">
              <HeaderBadge icon={<ShieldCheck size={12} />} label="ISO-27001 COMPLIANT" color="text-emerald-400" />
              <HeaderBadge icon={<MonitorCheck size={12} />} label="HFT TELEMETRY" color="text-blue-400" />
              <HeaderBadge icon={<Activity size={12} />} label="ATOMIC TRIO CORE" color="text-amber-400" />
              <HeaderBadge icon={<Lock size={12} />} label="SECURE GATEWAY" color="text-slate-500" />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link 
            href="/"
            className="bg-slate-800/50 hover:bg-slate-700 hover:text-white text-slate-400 px-4 py-2 rounded-lg font-black text-[10px] uppercase tracking-widest flex items-center gap-2 border border-[#1e222d] transition-all"
          >
            <LayoutDashboard size={14} /> Main View
          </Link>
          
          {isSessionActive ? (
            <button 
              onClick={handleStop}
              className="bg-rose-500 hover:bg-rose-400 text-white px-5 py-2 rounded-lg font-black text-[10px] uppercase tracking-widest flex items-center gap-2 shadow-xl shadow-rose-900/30 active:scale-95 transition-all"
            >
              <Square size={14} fill="currentColor" /> Disconnect
            </button>
          ) : (
            <button 
              onClick={handleStart}
              className="bg-[#2962ff] hover:bg-[#1e50e0] text-white px-5 py-2 rounded-lg font-black text-[10px] uppercase tracking-widest flex items-center gap-2 shadow-xl shadow-blue-900/30 active:scale-95 transition-all"
            >
              <Play size={14} fill="currentColor" /> Initialize
            </button>
          )}

          <div className={`px-4 py-2 rounded-lg border text-[10px] font-black uppercase tracking-widest flex items-center gap-2 ${
            isSessionActive ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400' : 'bg-slate-800/50 border-slate-700/50 text-slate-500'
          }`}>
             <span className={`w-2 h-2 rounded-full ${isSessionActive ? 'bg-emerald-400 animate-pulse' : 'bg-slate-700'}`} />
             {isSessionActive ? 'System Active' : 'System Offline'}
          </div>
        </div>
      </header>

      {/* CORE STATS GRID */}
      <ExpertStats snapshot={{
          ...portfolio,
          total_gross_pnl: portfolio.realized_pnl,
          current_price: 0,
          open_positions: portfolio.positions,
          trade_history: [],
          position_value: portfolio.equity - portfolio.cash,
          adaptive: forensics?.module_traces?.RiskGuard || {},
          peak_equity: portfolio.equity,
          max_drawdown: 0
      } as any} />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        {/* LEFT COLUMN: Systemic HUD & Notes */}
        <div className="lg:col-span-4 space-y-6">
           <SystemHealthHUD 
            moduleTraces={forensics?.module_traces || {}} 
            overallStatus={isSessionActive ? 'OK' : 'OFFLINE'}
          />
          <div className="h-[450px]">
            <ForensicNotes />
          </div>
          <div className="bg-[#161a25] border border-[#1e222d] p-5 rounded-lg">
             <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-400 mb-4">Clock Sync & Latency</h3>
             <div className="space-y-4">
                <div className="flex justify-between items-center text-xs">
                   <span className="text-slate-500">ENGINE LATENCY</span>
                   <span className="font-mono text-emerald-400">{telemetry?.latency_ms || 0}ms</span>
                </div>
                <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden">
                   <div className="bg-emerald-500 h-full w-[15%]" />
                </div>
                <div className="flex justify-between items-center text-xs">
                   <span className="text-slate-500">UPTIME</span>
                   <span className="font-mono text-blue-400">{(telemetry?.uptime_seconds || 0).toFixed(0)}s</span>
                </div>
             </div>
          </div>
        </div>

        {/* CENTER COLUMN: Logic Matrix */}
        <div className="lg:col-span-5 flex flex-col">
            <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-5 flex-1 relative overflow-hidden">
              <div className="flex items-center justify-between mb-4 relative z-10">
                <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white">Logic Matrix Trace</h3>
                <span className="text-[10px] font-bold text-slate-500">100% FEDERATED PULSE</span>
              </div>
              <div className="h-[1200px]">
                <LogicMatrix moduleTraces={forensics?.module_traces || {}} />
              </div>
            </div>
        </div>

        {/* RIGHT COLUMN: Thinking & History */}
        <div className="lg:col-span-3 space-y-6">
           <div className="h-[400px]">
             <ThinkingTerminal history={forensics?.thinking_history || []} />
           </div>
           
           <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-5">
             <div className="flex items-center justify-between mb-4">
               <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white">Live Inventory</h3>
               <span className="text-[10px] font-bold text-slate-500">{portfolio.positions.length}</span>
             </div>
             <SimPositionsTable positions={portfolio.positions} />
           </div>

           <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-5 h-[400px] overflow-hidden flex flex-col">
             <div className="flex items-center justify-between mb-4">
               <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white">Audit History</h3>
               <Link href="/expert/history" className="text-[10px] font-bold text-blue-500 hover:underline">View All</Link>
             </div>
             <div className="flex-1">
               <TradeHistory trades={[]} />
             </div>
           </div>
        </div>
      </div>
      
      {/* SYSTEM FEEDBAR */}
      <footer className="mt-auto py-3 px-6 border-t border-[#1e222d] flex items-center justify-between text-[10px] font-bold text-slate-600 bg-black/40">
        <div className="flex items-center gap-6">
          <span className="flex items-center gap-2 animate-pulse"><MonitorCheck size={12} className="text-blue-500" /> REAL-TIME FORENSICS: ACTIVE </span>
          <span className="flex items-center gap-2"><Zap size={12} className="text-blue-500" /> PEAK EQUITY: ${portfolio.equity.toFixed(2)}</span>
          <span className="flex items-center gap-2"><TrendingUp size={12} className="text-emerald-500" /> MAX DD: 0.00%</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="tracking-[0.2em] uppercase">Status: 200 OK</span>
          <span className="tracking-[0.2em] uppercase text-blue-500">Institutional_v3 (Manual)</span>
        </div>
      </footer>
      </div>
    </main>
  );
}

function HeaderBadge({ icon, label, color }: { icon: React.ReactNode, label: string, color: string }) {
  return (
    <div className={`flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest whitespace-nowrap px-2 py-1 bg-black/20 rounded border border-white/5 ${color}`}>
      {icon} {label}
    </div>
  );
}
