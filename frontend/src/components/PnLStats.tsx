"use client";

import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Activity, BarChart3, Gauge, Target, Shield, Zap } from 'lucide-react';

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
  // Safety guards for all inputs
  const eq = equity ?? 1000;
  const csh = cash ?? 1000;
  const pnl = realizedPnl ?? 0;
  const gross = totalGrossPnl ?? 0;
  const comms = totalCommissions ?? 0;
  const price = currentPrice ?? 0;
  const posVal = positionValue ?? 0;
  const peakEq = peakEquity ?? 1000;
  const mdd = maxDrawdown ?? 0;
  
  const pnlChange = eq - 1000;
  const pnlPct = ((pnlChange / 1000) * 100).toFixed(2);

  return (
    <div className="space-y-4">
      {/* Main Equity Card - Premium Overhaul */}
      <div className="bg-[#161a25] border border-[#1e222d] rounded-xl p-5 shadow-2xl relative overflow-hidden group">
        {/* Abstract Background Glow */}
        <div className={`absolute -top-24 -right-24 w-48 h-48 rounded-full blur-[80px] transition-all duration-700 ${
          pnlChange >= 0 ? 'bg-blue-500/20 group-hover:bg-blue-500/30' : 'bg-rose-500/20 group-hover:bg-rose-500/30'
        }`} />
        
        <div className="flex items-center justify-between mb-4 relative z-10">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <DollarSign size={18} className="text-blue-400" />
            </div>
            <div>
              <span className="text-[10px] uppercase font-black text-slate-500 tracking-[0.2em]">Total Equity</span>
              <p className="text-[9px] text-slate-600 font-mono">Real-time Valuation</p>
            </div>
          </div>
          <div className={`px-3 py-1 rounded-full text-[10px] font-black tracking-wider ${
            pnlChange >= 0 
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
          }`}>
            {pnlChange >= 0 ? '↑' : '↓'} {Math.abs(Number(pnlPct))}%
          </div>
        </div>

        <div className={`text-4xl font-black font-mono tracking-tighter mb-6 relative z-10 ${
          pnlChange >= 0 ? 'text-white' : 'text-rose-400'
        }`}>
          ${equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>

        {/* Improved Breakdown UI */}
        <div className="space-y-2 relative z-10">
          <div className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.03]">
            <div className="flex items-center gap-2">
              <Zap size={12} className="text-slate-500" />
              <span className="text-[10px] text-slate-400 font-bold uppercase">Funds in Trade</span>
            </div>
            <span className="text-xs font-mono font-bold text-blue-400">-${positionValue.toFixed(2)}</span>
          </div>
          
          <div className="flex items-center justify-between p-3 rounded-lg bg-[#2962ff]/10 border border-[#2962ff]/20 shadow-inner">
            <div className="flex items-center gap-2">
              <Shield size={14} className="text-blue-400" />
              <span className="text-[11px] text-blue-100 font-black uppercase">Available Cash</span>
            </div>
            <span className="text-base font-mono font-black text-white">${cash.toFixed(2)}</span>
          </div>

          <div className="flex items-center justify-between px-2 pt-2">
            <div className="flex items-center gap-1.5 opacity-40">
              <TrendingUp size={10} className="text-slate-400" />
              <span className="text-[9px] text-slate-500 uppercase font-black tracking-widest">Portfolio Peak</span>
            </div>
            <span className="text-[10px] font-mono text-slate-600 font-bold">${peakEquity.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Optimized 2x2 Grid - Accounting Breakdown */}
      <div className="grid grid-cols-2 gap-3">
        {/* Gross Market PnL Card */}
        <div className="bg-[#161a25] border border-[#1e222d] rounded-xl p-3.5 hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <div className={`p-1.5 rounded-md ${(totalGrossPnl || 0) >= 0 ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
              <BarChart3 size={14} className={(totalGrossPnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
            </div>
            <span className="text-[9px] uppercase font-black text-slate-500 tracking-widest">Market Move</span>
          </div>
          <div className={`text-lg font-black font-mono ${(totalGrossPnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {(totalGrossPnl || 0) >= 0 ? '+$' : '-$'}{Math.abs(totalGrossPnl || 0).toFixed(2)}
          </div>
          <div className="text-[8px] font-bold text-slate-600 uppercase mt-0.5">Gross (Before Fees)</div>
        </div>

        {/* Commissions Card */}
        <div className="bg-[#161a25] border border-[#1e222d] rounded-xl p-3.5 hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 bg-amber-500/10 rounded-md">
              <Activity size={14} className="text-amber-400" />
            </div>
            <span className="text-[9px] uppercase font-black text-slate-500 tracking-widest text-nowrap">Perf Fee (15%)</span>
          </div>
          <div className="text-lg font-black font-mono text-amber-400/90 [text-shadow:0_0_10px_rgba(251,191,36,0.1)]">
            -${(totalCommissions || 0).toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 4 })}
          </div>
          <div className="text-[8px] font-bold text-slate-600 uppercase mt-0.5">Aggregated Friction</div>
        </div>

        {/* Net Outcome Card (Market + Fees) */}
        <div className="bg-[#1c2130] border border-blue-500/30 rounded-xl p-3.5 hover:border-blue-500/50 transition-colors shadow-lg col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={`p-1.5 rounded-md ${realizedPnl >= 0 ? 'bg-emerald-500/20' : 'bg-rose-500/20'}`}>
                {realizedPnl >= 0 ? <TrendingUp size={16} className="text-emerald-400" /> : <TrendingDown size={16} className="text-rose-400" />}
              </div>
              <div>
                <span className="text-[10px] uppercase font-black text-blue-400 tracking-widest">Total Net Outcome</span>
                <p className="text-[8px] text-slate-500 uppercase font-bold">Calculation: Market + Fees</p>
              </div>
            </div>
            <div className={`text-xl font-black font-mono ${realizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {realizedPnl >= 0 ? '+$' : '-$'}{Math.abs(realizedPnl).toFixed(2)}
            </div>
          </div>
        </div>

        {/* BTC Price Card */}
        <div className="bg-[#161a25] border border-[#1e222d] rounded-xl p-3.5 hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-2 mb-2 text-slate-500">
            <div className="p-1.5 bg-blue-500/10 rounded-md">
              <Zap size={14} className="text-blue-400" />
            </div>
            <span className="text-[9px] uppercase font-black tracking-widest">Current Price</span>
          </div>
          <div className="text-lg font-black font-mono text-slate-200">
            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        {/* Drawdown Card */}
        <div className="bg-[#161a25] border border-[#1e222d] rounded-xl p-3.5 hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <div className={`p-1.5 rounded-md ${maxDrawdown > 5 ? 'bg-rose-500/10' : 'bg-amber-500/10'}`}>
              <Gauge size={14} className={maxDrawdown > 5 ? 'text-rose-400' : 'text-amber-400'} />
            </div>
            <span className="text-[9px] uppercase font-black text-slate-500 tracking-widest">Max Drawdown</span>
          </div>
          <div className={`text-lg font-black font-mono ${maxDrawdown > 5 ? 'text-rose-400' : 'text-amber-400'}`}>
            {(maxDrawdown * 100).toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Adaptive Strategy Stats */}
      <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[#1e222d]">
          <Zap size={14} className="text-amber-400" />
          <span className="text-xs font-bold uppercase text-slate-400">Adaptive Strategy</span>
        </div>
        
        <div className="space-y-2.5">
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Win Rate</span>
            <span className={`text-xs font-bold ${adaptive.win_rate >= 0.5 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {(adaptive.win_rate * 100).toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">W / L</span>
            <span className="text-xs font-medium text-slate-300">
              <span className="text-emerald-400">{adaptive.total_wins}</span>
              {' / '}
              <span className="text-rose-400">{adaptive.total_losses}</span>
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Streak</span>
            <span className="text-xs font-medium">
              {adaptive.win_streak > 0 ? (
                <span className="text-emerald-400">{adaptive.win_streak}W</span>
              ) : adaptive.loss_streak > 0 ? (
                <span className="text-rose-400">{adaptive.loss_streak}L</span>
              ) : (
                <span className="text-slate-500">—</span>
              )}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500 flex items-center gap-1"><Target size={12} /> TP</span>
            <span className="text-xs font-mono text-emerald-400">+{(adaptive.take_profit_pct * 100).toFixed(2)}%</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500 flex items-center gap-1"><Shield size={12} /> SL</span>
            <span className="text-xs font-mono text-rose-400">-{(adaptive.stop_loss_pct * 100).toFixed(2)}%</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">Pos Size</span>
            <span className="text-xs font-mono text-blue-400">{(adaptive.position_size_pct * 100).toFixed(1)}%</span>
          </div>
          <div className="flex justify-between items-center pt-1 border-t border-[#1e222d]">
            <span className="text-xs font-bold text-slate-400">Expected Value</span>
            <span className={`text-xs font-bold ${adaptive.expected_value >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ${adaptive.expected_value.toFixed(2)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
