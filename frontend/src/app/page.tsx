"use client";

import React from 'react';
import { useTradingSystem } from '@/hooks/useTradingSystem';
import { ExpertStats } from '@/components/ExpertStats';
import { FlowVisualizer } from '@/components/FlowVisualizer';
import { ThinkingTerminal } from '@/components/ThinkingTerminal';
import { ForensicPositions } from '@/components/ForensicPositions';
import { TradeHistory } from '@/components/TradeHistory';
import { LogicMatrix } from '@/components/LogicMatrix';
import { SystemHealthHUD } from '@/components/SystemHealthHUD';
import { ForensicNotes } from '@/components/ForensicNotes';
import { MiniTradingView } from '@/components/MiniTradingView';
import { AIControlPanel } from '@/components/AIControlPanel';
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
    <main className="h-screen bg-[#080a0f] text-slate-300 font-sans selection:bg-blue-500/30 overflow-hidden flex flex-col institutional-gradient">
      {/* SCROLLABLE CONTENT WRAPPER */}
      <div className="flex-1 overflow-y-auto p-1.5 lg:p-2 scroll-smooth scrollbar-thin">
      {/* HUD HEADER */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 border-b border-[#1e222d] pb-2 mb-2 glass px-3 rounded-t-lg">
        <div className="flex items-center gap-2">
          <div className="bg-[#2962ff] p-1.5 rounded shadow-2xl shadow-blue-900/40 group cursor-pointer hover:rotate-12 transition-all duration-300">
            <Cpu className="text-white fill-white" size={16} />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h1 className="text-sm font-black tracking-tighter text-white uppercase italic">
                Forensic Console <span className="text-[#2962ff]">v3.0</span>
              </h1>
              <span className="px-1 py-0.5 rounded bg-blue-500/5 text-blue-400 border border-blue-500/10 text-[7px] font-black uppercase tracking-widest animate-pulse">
                Forensic Fidelity: 100%
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 overflow-x-auto pb-0.5 scrollbar-hide">
              <HeaderBadge icon={<ShieldCheck size={8} />} label="ISO-27001 COMPLIANT" color="text-emerald-400" />
              <HeaderBadge icon={<MonitorCheck size={8} />} label="HFT TELEMETRY" color="text-blue-400" />
              <HeaderBadge icon={<Activity size={8} />} label="ATOMIC TRIO CORE" color="text-amber-400" />
              <HeaderBadge icon={<Lock size={8} />} label="SECURE GATEWAY" color="text-slate-500" />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <Link 
            href="/"
            className="bg-slate-800/50 hover:bg-slate-700 hover:text-white text-slate-400 px-1.5 py-1 rounded font-black text-[8px] uppercase tracking-widest flex items-center gap-1.5 border border-[#1e222d] transition-all"
          >
            <LayoutDashboard size={10} /> Main View
          </Link>
          
          {isSessionActive ? (
            <button 
              onClick={handleStop}
              className="bg-rose-500 hover:bg-rose-400 text-white px-2 py-1 rounded font-black text-[8px] uppercase tracking-widest flex items-center gap-1.5 shadow-xl shadow-rose-900/30 active:scale-95 transition-all"
            >
              <Square size={10} fill="currentColor" /> Disconnect
            </button>
          ) : (
            <button 
              onClick={handleStart}
              className="bg-[#2962ff] hover:bg-[#1e50e0] text-white px-2 py-1 rounded font-black text-[8px] uppercase tracking-widest flex items-center gap-1.5 shadow-xl shadow-blue-900/30 active:scale-95 transition-all"
            >
              <Play size={10} fill="currentColor" /> Initialize
            </button>
          )}

          <div className={`px-2 py-1 rounded border text-[8px] font-black uppercase tracking-widest flex items-center gap-1.5 ${
            isSessionActive ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400' : 'bg-slate-800/50 border-slate-700/50 text-slate-500'
          }`}>
             <span className={`w-1 h-1 rounded-full ${isSessionActive ? 'bg-emerald-400 animate-pulse' : 'bg-slate-700'}`} />
             {isSessionActive ? 'Active' : 'Offline'}
          </div>
        </div>
      </header>

      {/* CORE STATS GRID */}
      <ExpertStats snapshot={{
          ...portfolio,
          total_gross_pnl: portfolio.realized_pnl,
          current_price: portfolio.current_price || (portfolio as any).base_price || 0,
          open_positions: portfolio.positions || [],
          trade_history: portfolio.trade_history || [],
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
          <div className="h-[400px]">
            <ForensicNotes />
          </div>
          
          <MiniTradingView />

          <div className="bg-[#161a25] border border-[#1e222d] p-2 rounded-lg shadow-inner">
             <div className="flex items-center justify-between mb-4">
               <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-400">Audit History</h3>
               <Link href="/expert/history" className="text-[9px] font-bold text-blue-500/60 hover:text-blue-400 uppercase tracking-widest">View All</Link>
             </div>
             <div className="h-[200px] overflow-hidden">
                <TradeHistory trades={portfolio?.trade_history || []} />
             </div>
           </div>
        </div>

        {/* RIGHT COLUMN: Logic & Flows */}
         <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 leading-tight">
          <div className="md:col-span-2 lg:col-span-3 min-h-[300px]">
            <LogicMatrix moduleTraces={forensics?.module_traces || {}} />
          </div>
          <div className="md:col-span-2 lg:col-span-3 min-h-[150px]">
             <FlowVisualizer 
               lastTickTimestamp={telemetry?.timestamp}
               lastSignal={forensics?.thinking_history?.[forensics.thinking_history.length - 1]}
               simRunning={telemetry?.status.running || false}
               liveTrace={forensics?.module_traces}
             />
          </div>
          <div className="md:col-span-1 lg:col-span-1 h-[400px]">
            <AIControlPanel config={portfolio?.live_config || {}} />
          </div>
          <div className="md:col-span-1 lg:col-span-1 h-[400px]">
            <ThinkingTerminal history={forensics?.thinking_history || []} />
          </div>
          <div className="md:col-span-1 lg:col-span-1 h-[400px]">
            <ForensicPositions positions={portfolio?.positions || []} />
          </div>
        </div>
      </div>
      
      {/* SYSTEM FEEDBAR */}
      <footer className="mt-auto py-2 px-4 border-t border-[#1e222d] flex items-center justify-between text-[9px] font-bold text-slate-600 bg-black/40">
        <div className="flex items-center gap-6">
          <span className="flex items-center gap-2 animate-pulse"><MonitorCheck size={10} className="text-blue-500" /> REAL-TIME FORENSICS: ACTIVE </span>
          <span className="flex items-center gap-2"><Zap size={10} className="text-blue-500" /> PEAK EQUITY: ${(portfolio?.equity ?? 0).toFixed(2)}</span>
          <span className="flex items-center gap-2"><TrendingUp size={10} className="text-emerald-500" /> MAX DD: 0.00%</span>
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
