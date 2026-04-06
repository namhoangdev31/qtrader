"use client";

import React from 'react';
import { ArrowUpRight, ArrowDownRight, Clock, Target, Shield, TrendingUp, TrendingDown } from 'lucide-react';

interface TradeRecord {
  trade_id: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  entry_time: string;
  exit_time: string;
  pnl: number;
  pnl_pct: number;
  commission: number;
  reason: string;
  stop_loss: number;
  take_profit: number;
}

interface TradeHistoryProps {
  trades: TradeRecord[];
}

export const TradeHistory: React.FC<TradeHistoryProps> = ({ trades }) => {
  const sorted = [...trades].sort((a, b) => 
    new Date(b.exit_time).getTime() - new Date(a.exit_time).getTime()
  );

  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const wins = trades.filter(t => t.pnl > 0).length;
  const losses = trades.filter(t => t.pnl <= 0).length;

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded-lg overflow-hidden shadow-lg">
      <div className="flex items-center justify-between p-4 border-b border-[#1e222d] bg-[#1c222e]">
        <div className="flex items-center gap-2">
          <Clock size={18} className="text-[#2962ff]" />
          <h2 className="font-bold text-slate-200">Trade History</h2>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-slate-500">{trades.length} trades</span>
          <span className="text-emerald-400">{wins}W</span>
          <span className="text-rose-400">{losses}L</span>
          <span className={`font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-[#0a0c10] text-[#848e9c] uppercase text-xs font-bold border-b border-[#1e222d]">
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Entry</th>
              <th className="px-4 py-3">Exit</th>
              <th className="px-4 py-3">PnL</th>
              <th className="px-4 py-3">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e222d]">
            {sorted.length > 0 ? (
              sorted.map((trade) => (
                <tr key={trade.trade_id} className="hover:bg-[#1e222d] transition-colors">
                  <td className="px-4 py-3 text-slate-400 text-xs font-mono">
                    {new Date(trade.exit_time).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                      trade.side === 'BUY' 
                        ? 'bg-emerald-500/10 text-emerald-400' 
                        : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {trade.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                    ${trade.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                    ${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      {trade.pnl >= 0 ? (
                        <ArrowUpRight size={14} className="text-emerald-400" />
                      ) : (
                        <ArrowDownRight size={14} className="text-rose-400" />
                      )}
                      <span className={`font-bold text-xs ${
                        trade.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {trade.pnl >= 0 ? '+$' : '-$'}{Math.abs(trade.pnl).toFixed(2)}
                        <span className="text-slate-500 ml-1">({trade.pnl_pct >= 0 ? '+' : ''}{trade.pnl_pct.toFixed(2)}%)</span>
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`flex items-center gap-1 text-xs font-medium ${
                      trade.reason === 'TAKE_PROFIT' ? 'text-emerald-400' :
                      trade.reason === 'STOP_LOSS' ? 'text-rose-400' : 'text-blue-400'
                    }`}>
                      {trade.reason === 'TAKE_PROFIT' && <Target size={12} />}
                      {trade.reason === 'STOP_LOSS' && <Shield size={12} />}
                      {trade.reason === 'SIGNAL' && <TrendingUp size={12} />}
                      {trade.reason.replace('_', ' ')}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-500 italic">
                  No completed trades yet. Waiting for signals...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
