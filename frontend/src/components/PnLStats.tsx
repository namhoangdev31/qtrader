"use client";

import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  Activity, 
  BarChart3, 
  Gauge, 
  Target, 
  Shield, 
  Zap, 
  ArrowUpRight, 
  ArrowDownRight,
  PieChart,
  Percent,
  Clock,
  History
} from 'lucide-react';

interface PnLStatsProps {
  equity: number;
  cash: number;
  realizedPnl: number;
  totalGrossPnl: number;
  positionValue: number;
  totalCommissions: number;
  currentPrice: number;
  peakEquity: number;
  maxDrawdown: number;
  adaptive: {
    win_rate: number;
    total_wins: number;
    total_losses: number;
    win_streak: number;
    loss_streak: number;
    expected_value: number;
    stop_loss_pct: number;
    take_profit_pct: number;
    position_size_pct: number;
    max_drawdown_pct: number;
    total_trades: number;
  };
}

export const PnLStats: React.FC<PnLStatsProps> = ({
  equity,
  cash,
  realizedPnl,
  totalGrossPnl,
  positionValue,
  totalCommissions,
  currentPrice,
  peakEquity,
  maxDrawdown,
  adaptive,
}) => {
  // Safety guards
  const eq = equity ?? 1000;
  const csh = cash ?? 1000;
  const pnl = realizedPnl ?? 0;
  const gross = totalGrossPnl ?? 0;
  const comms = totalCommissions ?? 0;
  const posVal = positionValue ?? 0;
  const peakEq = peakEquity ?? 1000;
  const mdd = maxDrawdown ?? 0;
  
  const initialCapital = 1000;
  const pnlChange = eq - initialCapital;
  const pnlPct = ((pnlChange / initialCapital) * 100).toFixed(2);
  const isProfitable = pnlChange >= 0;

  // Derived Performance Metrics
  const winRate = adaptive?.win_rate ?? 0;
  const totalTrades = adaptive?.total_trades ?? 0;
  const profitFactor = adaptive?.total_wins > 0 && adaptive?.total_losses > 0 
    ? (adaptive.total_wins / adaptive.total_losses).toFixed(2) 
    : "1.00";

  return (
    <div className="flex flex-col gap-5">
      {/* 1. PRIMARY PERFORMANCE CARD (Glassmorphism) */}
      <div className="relative group p-6 rounded-2xl bg-[#161a25]/60 backdrop-blur-xl border border-[#1e222d] shadow-[0_20px_50px_rgba(0,0,0,0.5)] overflow-hidden transition-all hover:border-[#2962ff]/30">
        {/* Animated Glow Overlay */}
        <div className={`absolute -top-16 -right-16 w-48 h-48 rounded-full blur-[60px] opacity-20 transition-all duration-1000 group-hover:opacity-40 animate-pulse ${
          isProfitable ? 'bg-emerald-500' : 'bg-rose-500'
        }`} />

        <div className="flex items-center justify-between mb-6 relative z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#2962ff]/10 border border-[#2962ff]/20 flex items-center justify-center">
              <DollarSign size={20} className="text-[#2962ff]" />
            </div>
            <div>
              <h3 className="text-[10px] font-black uppercase text-slate-500 tracking-[0.2em]">Portfolio Equity</h3>
              <p className="text-[9px] text-slate-600 font-bold flex items-center gap-1">
                <Clock size={8} /> LIVE UPDATING
              </p>
            </div>
          </div>
          <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-black tracking-tight border ${
            isProfitable 
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
              : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
          }`}>
            {isProfitable ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {isProfitable ? '+' : ''}{pnlPct}%
          </div>
        </div>

        <div className="space-y-1 relative z-10 mb-8">
          <div className={`text-5xl font-black font-mono tracking-tighter ${isProfitable ? 'text-white' : 'text-rose-400'}`}>
            ${eq.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="flex items-center gap-2 text-xs font-bold">
            <span className="text-slate-500">Unrealized:</span>
            <span className={eq - csh >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {eq - csh >= 0 ? '+' : ''}${(eq - csh).toFixed(2)}
            </span>
          </div>
        </div>

        {/* High-Density Metric Row */}
        <div className="grid grid-cols-3 gap-2 relative z-10">
          <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.05] flex flex-col items-center">
            <span className="text-[9px] font-black text-slate-500 uppercase mb-1">Win Rate</span>
            <span className="text-sm font-black text-emerald-400 font-mono">{(winRate * 100).toFixed(1)}%</span>
            <div className="w-full h-1 bg-white/5 rounded-full mt-2 overflow-hidden">
              <div className="h-full bg-emerald-500 transition-all duration-500" style={{ width: `${winRate * 100}%` }} />
            </div>
          </div>
          <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.05] flex flex-col items-center">
            <span className="text-[9px] font-black text-slate-500 uppercase mb-1">Profit Factor</span>
            <span className="text-sm font-black text-blue-400 font-mono">{profitFactor}</span>
            <PieChart size={10} className="text-blue-500/40 mt-2" />
          </div>
          <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.05] flex flex-col items-center">
            <span className="text-[9px] font-black text-slate-500 uppercase mb-1">Max DD</span>
            <span className="text-sm font-black text-rose-400 font-mono">-{mdd.toFixed(2)}%</span>
            <Activity size={10} className="text-rose-500/40 mt-2" />
          </div>
        </div>
      </div>

      {/* 2. ADAPTIVE INTELLIGENCE METRICS */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#161a25]/60 backdrop-blur-xl border border-[#1e222d] rounded-2xl p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
             <div className="flex items-center gap-1.5">
               <Zap size={14} className="text-amber-400" />
               <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Signals</span>
             </div>
             <span className="text-xs font-mono font-bold text-white">{totalTrades} Executed</span>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-500 font-bold">Consecutive Wins</span>
              <span className="text-emerald-400 font-black">{adaptive?.win_streak ?? 0} MAX</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-500 font-bold">Consecutive Losses</span>
              <span className="text-rose-400 font-black">{adaptive?.loss_streak ?? 0} MAX</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-500 font-bold">Expected Value</span>
              <span className={(adaptive?.expected_value ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                {adaptive?.expected_value?.toFixed(4) ?? "0.0000"} / trade
              </span>
            </div>
          </div>
        </div>

        <div className="bg-[#161a25]/60 backdrop-blur-xl border border-[#1e222d] rounded-2xl p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
             <div className="flex items-center gap-1.5">
               <Shield size={14} className="text-blue-400" />
               <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Risk Limits</span>
             </div>
             <div className="px-1.5 py-0.5 rounded-sm bg-blue-500/20 text-[9px] font-black text-blue-400 border border-blue-500/30">ADAPTIVE</div>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-500 font-bold">Avg Stop Loss</span>
              <span className="text-rose-400 font-black">{adaptive?.stop_loss_pct ?? 0}%</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-500 font-bold">Avg Take Profit</span>
              <span className="text-emerald-400 font-black">{adaptive?.take_profit_pct ?? 0}%</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-500 font-bold">Fee Absorption</span>
              <span className="text-amber-500 font-black">{comms > 0 ? `-$${comms.toFixed(2)}` : "0.00%"}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. SESSION HISTORY GATEWAY (Placeholder for redesign) */}
      <button className="flex items-center justify-between p-4 rounded-2xl bg-[#161a25]/40 border border-[#1e222d] hover:bg-[#1e222d] transition-all group">
        <div className="flex items-center gap-3">
          <History size={18} className="text-slate-500 group-hover:text-blue-400 transition-colors" />
          <div className="text-left">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Archive</span>
            <p className="text-[11px] font-bold text-slate-400">View Forensic Reports</p>
          </div>
        </div>
        <ArrowUpRight size={18} className="text-slate-600 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
      </button>
    </div>
  );
};
