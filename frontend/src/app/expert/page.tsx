"use client";

import React from 'react';
import { useSimulation } from '@/hooks/useSimulation';
import { ExpertStats } from '@/components/ExpertStats';
import { FlowVisualizer } from '@/components/FlowVisualizer';
import { ThinkingTerminal } from '@/components/ThinkingTerminal';
import { SimPositionsTable } from '@/components/SimPositionsTable';
import { TradeHistory } from '@/components/TradeHistory';
import { LogicMatrix } from '@/components/LogicMatrix';
import { SystemHealthHUD } from '@/components/SystemHealthHUD';
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
  Cpu
} from 'lucide-react';
import Link from 'next/link';

export default function ExpertDashboard() {
  const { 
    simSnapshot, 
    simRunning, 
    activeSession, 
    handleSimStart, 
    handleSimStop,
    addLog
  } = useSimulation();

  const isSessionActive = activeSession || simRunning;
  const lastSignal = simSnapshot.thinking_history?.[simSnapshot.thinking_history.length - 1];

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
                Expert Console <span className="text-[#2962ff]">v2.1</span>
              </h1>
              <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[9px] font-black uppercase tracking-widest">
                High Density Mode
              </span>
            </div>
            <div className="flex items-center gap-4 mt-1.5 overflow-x-auto pb-1 scrollbar-hide">
              <HeaderBadge icon={<ShieldCheck size={12} />} label="ISO-27001 COMPLIANT" color="text-emerald-400" />
              <HeaderBadge icon={<Globe size={12} />} label="HFT LIQUIDITY" color="text-blue-400" />
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
              onClick={handleSimStop}
              className="bg-rose-500 hover:bg-rose-400 text-white px-5 py-2 rounded-lg font-black text-[10px] uppercase tracking-widest flex items-center gap-2 shadow-xl shadow-rose-900/30 active:scale-95 transition-all"
            >
              <Square size={14} fill="currentColor" /> Disconnect
            </button>
          ) : (
            <button 
              onClick={handleSimStart}
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
      <ExpertStats snapshot={simSnapshot} />

      {/* MODULE LOGIC PULSE & HEALTH HUD */}
      <section className="mt-6">
        <div className="flex items-center gap-2 mb-4">
          <Activity size={16} className="text-blue-500" />
          <h2 className="text-xs font-black uppercase tracking-[0.3em] text-white">Systemic Diagnostic pulse (Forensics)</h2>
        </div>
        
        {/* NEW HUD OVERVIEW */}
        <SystemHealthHUD 
          moduleTraces={simSnapshot.live_trace?.module_traces || {}} 
          overallStatus={simRunning ? (simSnapshot.live_trace?.overall_status || 'OK') : 'OFFLINE'}
        />

        <div className="h-[1300px] mb-6">
          <LogicMatrix moduleTraces={simSnapshot.live_trace?.module_traces || {}} />
        </div>
      </section>

      {/* MAIN CONTENT AREA */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        {/* LEFT COLUMN: Pipeline & Logic (Expert Only View) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="h-[350px]">
            <FlowVisualizer 
              simRunning={simRunning} 
              lastTickTimestamp={simSnapshot.thinking_history?.[simSnapshot.thinking_history.length - 1]?.timestamp}
              lastSignal={lastSignal}
              liveTrace={simSnapshot.live_trace}
            />
          </div>
          <div className="h-[550px]">
             <ThinkingTerminal history={simSnapshot.thinking_history || []} />
          </div>
        </div>

        {/* RIGHT COLUMN: Execution Details */}
        <div className="lg:col-span-7 space-y-6">
          {/* Active Positions Cluster */}
          <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white flex items-center gap-2">
                <LayoutDashboard size={14} className="text-blue-500" /> Real-time Inventory
              </h3>
              <span className="text-[10px] font-bold text-slate-500">{simSnapshot.open_positions.length} active positions</span>
            </div>
            <SimPositionsTable positions={simSnapshot.open_positions} />
          </div>

          {/* Historical Audit Cluster */}
          <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white flex items-center gap-2">
                <History size={14} className="text-blue-500" /> Tactical Trade Audit
              </h3>
              <div className="flex items-center gap-2">
                <div className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[9px] font-black">
                  WIN RATE: {simSnapshot.adaptive.win_rate.toFixed(1)}%
                </div>
                <div className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[9px] font-black">
                  PROFIT FACTOR: {(simSnapshot.adaptive.total_wins / (simSnapshot.adaptive.total_losses || 1)).toFixed(2)}
                </div>
              </div>
            </div>
            <TradeHistory trades={simSnapshot.trade_history} />
          </div>
        </div>
      </div>
      
      {/* SYSTEM FEEDBAR */}
      <footer className="mt-8 pt-4 border-t border-[#1e222d] flex items-center justify-between text-[10px] font-bold text-slate-600">
        <div className="flex items-center gap-6">
          <span className="flex items-center gap-2"><Zap size={12} className="text-blue-500" /> PEAK EQUITY: ${simSnapshot.peak_equity.toFixed(2)}</span>
          <span className="flex items-center gap-2"><TrendingUp size={12} className="text-emerald-500" /> MAX DD: {simSnapshot.adaptive.max_drawdown_pct.toFixed(2)}%</span>
          <span className="flex items-center gap-2"><BarChart3 size={12} className="text-blue-500" /> TOTAL TRADES: {simSnapshot.adaptive.total_trades}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="tracking-[0.2em] uppercase">Status: OK</span>
          <span className="tracking-[0.2em] uppercase">Environment: Institutional_v2</span>
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
